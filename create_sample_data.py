from textdb import TextDb

def quick_add(table, string):
    data = string.strip().split("\n")
    for item in data:
        table.add(item)

db = TextDb("testdata")

db.add("projects")

db.add("tasks")
db.tasks.add_property("done", "checkbox")

db.add("notes")

db.projects.add_relation("tasks")
db.projects.add_relation("notes")

quick_add(db.tasks, """
eat dinner
take out trash
brush cat
eat table
drink water
take meds
take vitamins
sleep
""")

quick_add(db.projects, """
health
mental health
apartment
""")
db.projects.add(name="relationtest", tasks=["sleep", "take vitamins"])

quick_add(db.notes, """
quick note
phonejot
oh no i forgot to order groceries again
my washing machine is broken
this is just test data
it really doesnt matter
""")

for table in db:
    print(table.name)
    for row in table:
        print(f"  - {row.name}")
        for key, value in row:
            print(f"    - {key}: {value}")

db.save()
