this is a python module that lets you interface with a database that consists of plain markdown text files.
the structure of such a database looks like:
```
database
  - .properties
    - table_1.yaml
  - table_1
    - first_item.md
    - second_item.md
```

every markdown file has properties at the top, as well as the normal content of the file below it. that looks like this:
```markdown
---
pinned: true
url: https://www.somewebsitesomewhere.com
---
# notacular
hi! i'm a note
full of *content*
wow!
```

the properties of each table is defined in a simple human-readable yaml file, which looks like:
```
pinned: checkbox
url: text
```
yes, that's literally just the name of each property and the type!

it's completely human-readable and future-proof

example:

```python
import textdb

# the folder that the database will be stored in
DB_PATH = "maindb"

db = textdb.TextDb(DB_PATH)

# add table "notes" to the database
db.add("notes")

# add a property to that table, called "pinned", of type "checkbox" (internally that's a boolean)
# there's a few predefined types. if you try to create a property with a type that doesn't exist, it'll tell you what the valid types are
db.notes.add_property("pinned", "checkbox")

# it's simple
db.notes.add_property("url", "text")

# add our first note!
db.notes.add("notacular", pinned=True)

# you can also do it like this
db.notes.add(name="second note", pinned=False)

# or like this
db.notes.add("third note", True)

# we forgot to add a url, didn't we?
db.notes.edit("notacular", url="https://somewebsitesomewhere.com")

# let's not forget the content
db.notes.edit("notacular", content="""
# notacular
hi! i'm a note
full of *content*
wow!
""")

# you can then reach the item in these ways:
db.notes.notacular
db.notes['notacular']
db.notes.get("notacular")

# all of which will return
>> {'name': 'notacular', 'pinned': True, 'url': 'https://somewebsitesomewhere.com', 'content': <the content we added>}

# relations?! yes!
db.add("projects")
db.projects.add_relation("notes")

# you can do it like this
db.projects.add("neatproject", notes=["notacular"])

# or like this
db.projects.neatproject.notes.add("second note")

# watch the magic happen
db.save()
```