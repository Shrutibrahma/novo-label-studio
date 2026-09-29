"""Demo data for development: ~50 sample parts (run via scripts/demo.ps1; never part of the product).

Idempotent: parts that already exist are left alone. Requires first-run setup to be done, because every row
needs an owner (created_by)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.audit import audit
from app.db import dispose_engine, init_engine, sessionmaker
from app.models import AppUser, CustomFieldDef, Part, PartAlias
from app.parts.values import normalize_part_number

MATERIAL = ("material", "Material")

# (part number, part name, description, revision, material, label name)
PARTS: list[tuple[str, str, str | None, str | None, str | None, str | None]] = [
    ("NP-10421", "Bearing Housing", "Cast iron pillow block housing", "C", "Cast iron", "10-32 x 1/2 16"),
    ("NP-10422", "Bearing Cap", "Top cap for NP-10421", "B", "Cast iron", None),
    ("NP-10430", "Deep Groove Ball Bearing", "6204-2RS sealed bearing, 20 mm bore", "A", "Chrome steel", "6204-2RS"),
    ("NP-10431", "Deep Groove Ball Bearing", "6205-2RS sealed bearing, 25 mm bore", "A", "Chrome steel", "6205-2RS"),
    ("NP-10440", "Shaft Collar", "Set-screw collar, 20 mm", "A", "Steel, black oxide", None),
    ("NP-10441", "Shaft Collar", "Two-piece clamp collar, 25 mm", "B", "Aluminium", None),
    ("NP-10450", "Drive Shaft", "Keyed drive shaft, 20 mm x 300 mm", "D", "1045 steel", None),
    ("NP-10451", "Idler Shaft", "Plain shaft, 20 mm x 250 mm", "C", "1045 steel", None),
    ("NP-10460", "Timing Pulley", "HTD 5M, 24 teeth, 20 mm bore", "A", "Aluminium", None),
    ("NP-10461", "Timing Belt", "HTD 5M, 25 mm wide, 800 mm", "A", "Neoprene", None),
    ("NP-10470", "Motor Mount Plate", "NEMA 23 mount, slotted", "B", "Aluminium", None),
    ("NP-10471", "Motor Mount Bracket", "90-degree bracket for NEMA 23", "A", "Steel, zinc plated", None),
    ("NP-10480", "Linear Rail", "15 mm profile rail, 600 mm", "A", "Hardened steel", None),
    ("NP-10481", "Linear Carriage", "15 mm flanged carriage", "A", "Hardened steel", None),
    ("NP-10490", "Coupling", "Jaw coupling, 14 mm to 20 mm", "B", "Aluminium", None),
    ("NP-10500", "Spider Insert", "Jaw coupling insert, 92A", "A", "Polyurethane", None),
    ("NP-20100", "Socket Head Cap Screw", "M6 x 20, class 12.9", None, "Alloy steel", "M6 x 20 SHCS"),
    ("NP-20101", "Socket Head Cap Screw", "M6 x 30, class 12.9", None, "Alloy steel", "M6 x 30 SHCS"),
    ("NP-20102", "Socket Head Cap Screw", "M8 x 25, class 12.9", None, "Alloy steel", "M8 x 25 SHCS"),
    ("NP-20110", "Machine Screw", "10-32 x 3/4 pan head Phillips", None, "Stainless 18-8", None),
    ("NP-20111", "Machine Screw", "10-24 x 1/2 pan head Phillips", None, "Stainless 18-8", "10-24 x 1/2 16"),
    ("NP-20120", "Hex Nut", "M6, class 8", None, "Steel, zinc plated", None),
    ("NP-20121", "Hex Nut", "M8, class 8", None, "Steel, zinc plated", None),
    ("NP-20122", "Nylon Insert Lock Nut", "10-32", None, "Stainless 18-8", None),
    ("NP-20130", "Flat Washer", "M6, DIN 125", None, "Steel, zinc plated", None),
    ("NP-20131", "Flat Washer", "M8, DIN 125", None, "Steel, zinc plated", None),
    ("NP-20132", "Split Lock Washer", "M6", None, "Spring steel", None),
    ("NP-20140", "Dowel Pin", "6 mm x 20 mm, h6", None, "Hardened steel", None),
    ("NP-20141", "Spring Pin", "4 mm x 24 mm", None, "Spring steel", None),
    ("NP-20150", "Threaded Insert", "M6 heat-set insert", None, "Brass", None),
    ("NP-30200", "Proximity Sensor", "M12 inductive, PNP NO, 4 mm range", "B", None, "PROX M12 PNP"),
    ("NP-30201", "Photoelectric Sensor", "Diffuse, 300 mm range, PNP", "A", None, None),
    ("NP-30210", "Limit Switch", "Roller lever, 1NO1NC", "A", None, None),
    ("NP-30220", "Cable Gland", "M20 x 1.5, IP68", None, "Nylon", None),
    ("NP-30221", "Cable Gland", "M16 x 1.5, IP68", None, "Nylon", None),
    ("NP-30230", "Terminal Block", "4 mm2 feed-through, DIN rail", "A", None, None),
    ("NP-30231", "End Stop", "DIN rail end clamp", None, None, None),
    ("NP-30240", "Relay", "24 VDC coil, SPDT, 10 A", "C", None, None),
    ("NP-30250", "Fuse Holder", "5 x 20 mm, panel mount", "A", None, None),
    ("NP-30260", "Emergency Stop Button", "40 mm mushroom head, twist release", "B", None, "E-STOP 40"),
    ("NP-40300", "Pneumatic Cylinder", "Bore 32 mm, stroke 100 mm", "D", "Aluminium", None),
    ("NP-40301", "Solenoid Valve", "5/2, 24 VDC, 1/4 NPT", "C", None, None),
    ("NP-40310", "Push-to-Connect Fitting", "1/4 tube x 1/8 NPT, straight", None, "Nickel-plated brass", None),
    ("NP-40311", "Push-to-Connect Fitting", "1/4 tube x 1/8 NPT, elbow", None, "Nickel-plated brass", None),
    ("NP-40320", "Pressure Regulator", "0-10 bar, with gauge", "A", None, None),
    ("NP-40330", "Silencer", "1/8 NPT sintered bronze", None, "Bronze", None),
    ("NP-50400", "Guard Panel", "Polycarbonate, 500 x 400 x 6 mm", "B", "Polycarbonate", None),
    ("NP-50401", "Guard Hinge", "Aluminium profile hinge, 40 series", "A", "Aluminium", None),
    ("NP-50410", "Extrusion", "40 x 40 T-slot, 1000 mm", "A", "Aluminium 6063", "40x40 1000"),
    ("NP-50411", "T-Nut", "M6, 40 series slot 8", None, "Steel, zinc plated", None),
    ("NP-50420", "Levelling Foot", "M12, 80 mm base, swivel", "A", "Steel / rubber", None),
    ("NP-50430", "Handle", "Tubular handle, 180 mm", "A", "Aluminium", None),
]


async def load() -> int:
    init_engine()
    try:
        async with sessionmaker()() as db:
            admin = (await db.execute(select(AppUser).where(AppUser.role == "admin", AppUser.active.is_(True))
                                      .order_by(AppUser.created_at))).scalars().first()
            if admin is None:
                print("Run first-time setup in the browser first (no admin account exists yet).", file=sys.stderr)
                return 1
            if await db.get(CustomFieldDef, MATERIAL[0]) is None:
                db.add(CustomFieldDef(key=MATERIAL[0], label=MATERIAL[1], data_type="text", choices=None,
                                      required=False, searchable=True, printable=True, sort_order=0))
                audit(db, admin.id, "field.create", "custom_field_def", MATERIAL[0], None,
                      {"key": MATERIAL[0], "label": MATERIAL[1], "data_type": "text", "searchable": True})
            existing = set((await db.execute(select(Part.part_number_norm))).scalars())
            added = 0
            for number, name, description, revision, material, label_name in PARTS:
                if normalize_part_number(number) in existing:
                    continue
                part = Part(part_number=number, part_name=name, description=description, revision=revision,
                            custom_data={MATERIAL[0]: material} if material else {}, source="manual",
                            created_by=admin.id, updated_by=admin.id)
                db.add(part)
                await db.flush()
                audit(db, admin.id, "part.create", "part", part.id, None,
                      {"part_number": number, "part_name": name, "source": "demo"})
                if label_name:
                    alias = PartAlias(part_id=part.id, alias=label_name, is_label_name=True, created_by=admin.id)
                    db.add(alias)
                    await db.flush()
                    audit(db, admin.id, "alias.create", "part_alias", alias.id, None,
                          {"part_id": part.id, "alias": label_name, "is_label_name": True})
                added += 1
            await db.commit()
            print(f"Demo data loaded: {added} new parts ({len(PARTS) - added} already existed).")
            return 0
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(load()))
