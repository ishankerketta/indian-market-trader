#!/usr/bin/env python3
"""Build one ZIP per skill for uploading to the Claude app (Customize > Skills > Upload a skill).

  python3 tools/build_app_zips.py            -> dist/india-scanner.zip, dist/india-levels.zip, ...

Each ZIP holds the skill folder with the shared library copied inside it, so it works on its
own. Claude Code users don't need this: install the plugin instead.
"""
import pathlib
import shutil
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
DIST = ROOT / "dist"


def main():
    DIST.mkdir(exist_ok=True)
    shared = [p for p in (SKILLS / "_shared").glob("*.py")]
    built = []
    for skill in sorted(SKILLS.glob("india-*")):
        if not (skill / "SKILL.md").exists():
            continue
        out = DIST / f"{skill.name}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(skill.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    z.write(f, f"{skill.name}/{f.relative_to(skill)}")
            for f in shared:
                z.write(f, f"{skill.name}/_shared/{f.name}")
        built.append(out.name)
    print(f"Built {len(built)} ZIPs in {DIST}: {', '.join(built)}")
    print("Upload each in the Claude app under Customize > Skills > + > Upload a skill, with code execution on.")
    print("Scripts fetch Yahoo, NSE, Google News and Reddit: allow those domains in your Claude settings, "
          "or they will be refused by Claude's sandbox.")


if __name__ == "__main__":
    main()
