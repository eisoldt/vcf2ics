#!/usr/bin/env python3
from dataclasses import dataclass
from pathlib import Path
from string import ascii_letters
from string import digits
import argparse
import random
import time
import sys
import hashlib
from datetime import datetime

# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# CONFIGURATION

PROGRAM_NAME = "VCF to ICS"
PROGRAM_VERSION = "1.0"
ADD_AGE = False

@dataclass
class Vcard:
    """holds elements of a vcard as information for ics file"""
    name: str
    dt_birth_start: datetime | None = None
    dt_birth_end: datetime | None = None
    birth_start_str = str | None
    uid: str | None = None
    age: int | None = None

    def set_birthday(self, bday):
        # BDAY format:
        # BDAY:2000-07-01T00:00:00
        # or   2000-07-01
        bday = bday.split("T")[0]  # '2000-07-01T000000'
        self.birth_start_str = bday.replace("-", "")
        year, month, day = bday.split("-")
        self.dt_birth_start = datetime(int(year), int(month), int(day))
        self.dt_birth_end = datetime(int(time.strftime("%Y")), int(month), int(day))  # current year!

        if ADD_AGE:
            dt_diff = self.dt_birth_end - self.dt_birth_start
            days = dt_diff.days + 1  # ein Tag zuwenig
            self.age = int(days / 365)

    def __str__(self):
        return f"{self.name}: {self.dt_birth_start} {self.dt_birth_end} {self.age}"

    @property
    def entry(self):
        if ADD_AGE:
            list_block = [f"BEGIN:VEVENT", f"DTSTART:{self.birth_start_str}", f"SUMMARY:{self.name} ({self.age})",
                        "RRULE:FREQ=YEARLY", "DURATION:P1D", f"UID:{self.uid}", "END:VEVENT"]
        else:
            list_block = [f"BEGIN:VEVENT", f"DTSTART:{self.birth_start_str}", f"SUMMARY:{self.name}",
                        "RRULE:FREQ=YEARLY", "DURATION:P1D", f"UID:{self.uid}", "END:VEVENT"]
        entry = "\n".join(list_block)
        return entry


def create_vcard(card: str) -> Vcard | None:
    working_dict = {}
    for line in card.split("\n"):
        if line.startswith("BDAY"):
            key, value = line.split(":", 1)
            working_dict["BDAY"] = value.strip()
        elif line.startswith("N:"):
            working_dict["N"] = line[2:].strip()
        elif line.startswith("FN:"):
            working_dict["FN"] = line[3:].strip()
        elif line.startswith("UID:"):
            working_dict["UID"] = line[4:].strip()
    try:
        bday = working_dict["BDAY"]
    except KeyError:
        return  # not usable

    try:  # prefer "N" over "FN"
        name = working_dict["N"]  # separate parts
    except KeyError:
        try:
            name = working_dict["FN"]  # one element
        except KeyError:  # no information
            return
    else:
        elems = name.split(";")
        if elems[3]:  # Dr.
            new_name = f"{elems[3]} {elems[1]} {elems[0]}"
        else:
            new_name = f"{elems[1]} {elems[0]}"
        name = new_name

    vcard = Vcard(name)
    vcard.set_birthday(bday)
    try:
        vcard.uid = working_dict["UID"]
    except KeyError:  # not a problem, can be generated later
        birth_start_str = vcard.dt_birth_start.strftime("%Y%m%d")
        vcard.uid = generate_uid(vcard.name, birth_start_str)

    return vcard


def generate_uid(name: str, birthday: str):
    """
    Generates a consistent UID based on the person's name and birthday.
    This ensures that the same person always receives the same UID,
    which can be useful when exporting recurring calendar entries.

    Parameters:
        name (str): The full name of the person.
        birthday (str): The birthday of the person, ideally in YYYYMMDD format.

    Returns:
        str: A SHA-256 based hexadecimal UID string.
    """
    base = f"{name}-{birthday}"
    uid_hash = hashlib.sha256(base.encode()).hexdigest()
    return uid_hash


def process() -> list[str] | None:
    # Read VCF file content
    file_content = vcf_file.read_text(encoding="utf-8")
    # Separate VCards
    vcards = file_content.split("END:VCARD")
    all_cards = [vcard.strip() + "\nEND:VCARD" for vcard in vcards if vcard.strip()]
    print(f"{len(all_cards)} VCards found")
    if not all_cards:
        return None

    formatted_entries = []
    for card in all_cards:
        vcard = create_vcard(card)
        if not vcard:
            continue
        print(f"- {vcard.birth_start_str}\t{vcard.age}\t{vcard.name}")
        formatted_entries.append(vcard.entry)
    # for
    print(f"\n{len(formatted_entries)} usable entries")
    return formatted_entries


def write_ics_file(ics_file: Path, calendar_name: str, list_formatted_entries: list[str]):
    with ics_file.open("w") as f:
        # Write ICS calendar header
        f.write(f"BEGIN:VCALENDAR\nPRODID:-//{PROGRAM_NAME}//NONSGML {calendar_name} V1.0//EN\n"
                f"X-WR-CALNAME:{calendar_name}\nVERSION:2.0\n")
        for entry in list_formatted_entries:
            f.write(f"{entry}\n")
        # Write ICS calendar footer
        f.write("END:VCALENDAR\n")
        print("\n->", ics_file)


if __name__ == "__main__":
    # Command-line interface
    argParser = argparse.ArgumentParser(description=f"{PROGRAM_NAME} {PROGRAM_VERSION}")
    argParser.add_argument('-i', '--input', metavar='PATH', help='Input .vcf file path', required=True)
    argParser.add_argument('-o', '--output', metavar='PATH', help='Output .ics file path', required=True)
    argParser.add_argument('-n', '--name', metavar='NAME', help='Desired calendar name', required=True)
    args = vars(argParser.parse_args())

    vcf_file = Path(args["input"])
    ics_file = Path(args["output"])
    calendar_name = args["name"]

    if not vcf_file.exists():
        print("Invalid input file path:", vcf_file)
        sys.exit(1)

    formatted_entries = process()
    if not formatted_entries:
        sys.exit(1)

    # Write ICS event:
    write_ics_file(ics_file, calendar_name, formatted_entries)
