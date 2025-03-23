import json  #dental headquarter

data = json.load(open("phrases.json", "r", encoding="utf-8"))

for item in data:
    print(f"{item['en']} = {item['nl']}")
    input("Press Enter for next...\n")


