from pathlib import Path

p = Path("templates/index.html")
s = p.read_text()

old = "Loan EMI Calculator"
new = "Loan EMI Calculator - Version 1.1"

if old not in s:
    raise SystemExit("Expected title text not found. No file changed.")

p.write_text(s.replace(old, new))
print("Application title updated successfully.")
