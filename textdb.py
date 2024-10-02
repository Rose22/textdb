import os
import shutil
import yaml
import datetime

# TODO: implement two-way relations
# TODO: implement relation auto-update when renaming properties in tables

def format_name(path):
    format_map = {
        " ": "_",
        ".": "-",
        "/": ""
    }

    for original, replacement in format_map.items():
        path = path.replace(original, replacement)

    return path

class TextTableRelation():
    """special table relation property"""

    def __init__(self, source_table, target_table, items=None):
        self.name = target_table
        self.type = TextTableRelation
        self.default_value = None
        self.source_table = source_table
        self.target_table = target_table
        self.type_s = f"relation:{self.target_table}"
        self._items = []
        if items:
            self._items = items

    def __repr__(self):
        return f"relation:{self.target_table}{repr(self._items)}"

    def __iter__(self):
        for item in self._items:
            yield item

    def __getitem__(self, item_name):
        if item_name in self._items:
            return self.source_table.parent.get_table(self.target_table).get(item_name)
    def __getattr__(self, item_name):
        return self.__getitem__(item_name)

    def add(self, item_name):
        item_name = format_name(item_name)

        target_table_obj = self.source_table.parent.get_table(self.target_table)
        for row in target_table_obj:
            if row.name == item_name:
                self._items.append(item_name)
                return True

        return False

    def delete(self, item_name):
        item_name = format_name(item_name)

        if item_name in self._items:
            del(self._items[self._items.index(item_name)])
            return True

        return False

def relation_representer(dumper, data):
    return dumper.represent_sequence('!relation', list(data))

def relation_constructor(loader, node):
    values = loader.construct_sequence(node)
    return TextTableRelation(None, None, values)

yaml.SafeLoader.add_constructor('!relation', relation_constructor)
yaml.SafeDumper.add_representer(TextTableRelation, relation_representer)

class TextTableProperty:
    """table property. has an internal map of types, so that the user can specify a type by text, but internally it gets converted to a python type"""

    typemap = {
        "text": str,
        "number": float,
        "date": datetime.datetime,
        "checkbox": bool,
        "select": list
    }

    defaults = {
        "text": "",
        "number": 0.0,
        "date": datetime.datetime,
        "checkbox": False,
        "select": []
    }

    def __init__(self, property_name, property_type):
        self.name = property_name
        self.type = property_type
        self.type_s = property_type

    def __str__(self):
        return self.name
    def __repr__(self):
        return(f"('{self.name}', {self.type})")

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, property_type):
        if property_type in self.typemap.keys():
            self._type = self.typemap[property_type]
        else:
            raise ValueError(f"type must be one of the following: {', '.join(self.typemap)}")

    @property
    def default_value(self):
        return self.defaults[self.type_s]

    def convert_from_str(self, value):
        converted = None

        match value.lower():
            case "false":
                converted = False
            case "true":
                converted = True
            case value.isnumeric():
                converted = float(value)

        return converted

class TextTableRow(dict):
    def __init__(self, parent_table, name):
        super(TextTableRow, self).__init__()
        # name is a special property that cannot be altered, because it is used as the filename. make sure we format it to a name that can be used on the filesystem.
        self.name = format_name(name)
        # also a special property that contains the content below all the user-defined properties
        self.content = str() 

        self.properties = {}
        self.parent = parent_table

    def __repr__(self):
        repr_dict = {"name": self.name} | self.properties | {"content": self.content}
        return repr(repr_dict)

    def __getitem__(self, key):
        if key in self.properties:
            return self.properties[key]
    def __getattr__(self, key):
        return self.__getitem__(key)

    def __iter__(self):
        for key, value in self.properties.items():
            yield (key, value)

    def resolve_path(self):
        return self.parent.parent.resolve_path(self)

    def convert_to_markdown(self):
        if self.properties:
            return(f"---\n{yaml.safe_dump(self.properties)}---\n{self.content}")
        else:
            return(self.content)

class TextTable:
    def __init__(self, parent_db, name):
        self.parent = parent_db

        self.name = name

        # each property has a name and a type
        self._properties = []
        # each row has multiple user assigned properties and a few special system properties
        self._rows = []

    def __iter__(self):
        for row in self._rows:
            yield row
    def __getitem__(self, key):
        return self.get(key)
    def __getattr__(self, key):
        return self.get(key)

    def __repr__(self):
        names = []
        for row in self:
            names.append(f"'{row.name}'")

        return f"[{', '.join(names)}]"

    def get_properties(self):
        return self._properties
    def _get_property_index(self, name):
        """get property index by name"""

        for index, prop in enumerate(self._properties):
            if prop.name == name:
                return index
    def get_property(self, name):
        """get property object by name"""

        return self._properties[self._get_property_index(name)]
    def get_property_names(self):
        """get a list of all the properties in this table"""

        return [prop.name for prop in self._properties]

    def add_property(self, property_name, property_type):
        """add a property to the table"""

        self._properties.append(TextTableProperty(property_name, property_type))
        self._update_rows()
    def edit_property(self, property_name, **kwargs):
        """edit an existing property. use keyword arguments to specify what to edit"""

        prop = self.get_property(property_name)
        if not prop:
            return False

        if "name" in kwargs.keys():
            prop.name = kwargs['name']
        if "type" in kwargs.keys():
            prop.type = kwargs['type']

        # rename the property across all rows, preserving property order
        for row in self._rows:
            new_properties = {}
            for prop_name, prop_value in row.properties.items():
                if prop_name == property_name:
                    prop_name = kwargs['name']

                new_properties[prop_name] = prop_value

            row.properties = new_properties
    def del_property(self, property_name):
        """delete a property from the table"""

        del(self._properties[self._get_property_index(property_name)])
        self._update_rows()

    def add_relation(self, target_table):
        """add a relation property that points to rows in a different table"""

        self._properties.append(TextTableRelation(self, target_table))
        self._update_rows()

    def _update_rows(self):
        """update rows to make sure everything reflects the table structure"""

        for row in self._rows:
            add_queue = []
            delete_queue = []

            for property_name in row.properties.keys():
                if property_name not in self.get_property_names():
                    delete_queue.append(property_name)
            for property_name in self.get_property_names():
                if property_name not in row.properties.keys():
                    add_queue.append(property_name)

            for property_name in delete_queue:
                del(row.properties[property_name])
            for property_name in add_queue:
                prop = self.get_property(property_name)
                if prop.type == TextTableRelation:
                    row.properties[property_name] = TextTableRelation(self, prop.target_table, [])
                    continue

                row.properties[property_name] = prop.default_value

    def add_row(self, *args, **kwargs):
        """add a row to the table. use keyword arguments to specify what values you want to add into the table's properties"""

        if len(args) > 0 and len(kwargs) == 0:
            kwargs = {}
            prop_names = ["name"] + self.get_property_names() + ["content"]

            for index, arg in enumerate(args):
                kwargs[prop_names[index]] = arg
        elif len(args) == 1 and len(kwargs) > 0:
            kwargs = {"name": args[0]} | kwargs

        if "name" not in kwargs.keys():
            raise ValueError("missing name argument")

        row = TextTableRow(self, kwargs['name'])

        # predefine all the properties regardless of content
        for prop in self._properties:
            if prop.type == TextTableRelation:
                row.properties[prop.name] = TextTableRelation(self, prop.target_table, [])
                continue

            row.properties[prop.name] = prop.default_value

        # put content into it's special little section
        if "content" in kwargs.keys():
            row.content = kwargs['content'].strip()

        # load the kwargs into the properties of the row
        for prop_name, value in kwargs.items():
            if prop_name in ["name", "content"]:
                continue
            if prop_name not in self.get_property_names():
                continue

            prop = self.get_property(prop_name)

            if not prop:
                raise ValueError(f"property {prop_name} does not exist")

            if type(value) != prop.type: 
                if type(value) is str:
                    value = prop.convert_from_str(value)
                elif prop.type is TextTableRelation:
                    # this is a special type of property with extra data..
                    if value is None:
                        continue

                    filtered_relation_values = []
                    for name in value:
                        filtered_relation_values.append(format_name(name))

                    value = TextTableRelation(self, prop.target_table, filtered_relation_values)
                elif value is None:
                    pass
                else:
                    raise TypeError(f"{prop.name} should be of type {prop.type}, but is {type(value)}") 

            row.properties[prop_name] = value

        self._rows.append(row)
    def add(self, *args, **kwargs):
        """alias for add_row"""

        return self.add_row(*args, **kwargs)

    def _get_row_index(self, target_property, target_value):
        """get the index of a row. used internally by the class"""

        for index, row in enumerate(self._rows):
            if target_property == "name":
                if row.name == target_value:
                    return index
            elif target_property == "content":
                if row.content == target_value:
                    return index
            else:
                if row.properties[target_property] == target_value:
                    return index

        return None
    def get_row(self, *args):
        """get a row. you can either get it by name, or get it by a specified property"""

        if len(args) > 1:
            target_property = args[0]
            target_value = args[1]
        else:
            target_property = "name"
            target_value = args[0]

        index = self._get_row_index(target_property, target_value)
        if index is None:
            return None

        return self._rows[index]
    def get(self, *args):
        """alias for get_row"""

        return self.get_row(*args)

    def edit_row(self, row_name, **kwargs):
        """edit a row. use keyword arguments to specify what to edit"""

        row = self.get_row("name", row_name)
        if row is None:
            raise IndexError(f"row {row_name} not found")

        for prop_name, prop_value in kwargs.items():
            if prop_name == "content":
                row.content = prop_value.strip()
                continue

            if prop_name in row.properties.keys():
                row.properties[prop_name] = prop_value
    def edit(self, row, **kwargs):
        """alias for edit_row"""

        return self.edit_row(row, **kwargs)

    def delete_row(self, row_name):
        """delete a row from the table"""

        index = self._get_row_index("name", row_name)
        if index is None:
            return False
        
        del(self._rows[index])
    def delete(self, row_name):
        """alias for delete_row"""

        return self.delete_row(row_name)
        
    def resolve_path(self):
        return self.parent.resolve_path(self)

    def load(self):
        # load row properties from the appropriate file
        self.load_properties()

        filelist = os.listdir(self.resolve_path())
        for filename in filelist:
            filepath = f"{self.resolve_path()}/{filename}"
            self.load_values(filepath)

        return self


    def load_properties(self):
        filepath = f"{self.parent.resolve_path()}/.properties/{self.name}.yaml"

        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"{filepath} not found! can't load properties")

        with open(filepath, 'r') as f:
           file = f.read()

        if not file:
            return False

        loaded_properties = yaml.safe_load(file)

        for key, value in loaded_properties.items():
            if type(value) is str and value.startswith("relation:"):
                # this is a relation. it's a different beast to handle!
                target_table = value[9:] #TODO: find a safer way to do this
                self.add_relation(target_table)
            else:
                self.add_property(key, value)

    def load_values(self, filepath):
        yaml_found = False
        yaml_end = 0

        file = ""
        with open(filepath, 'r') as f:
            file = f.read().strip()

        file_lines = file.split("\n")

        for line_num, line in enumerate(file_lines):
            if line_num == 0 and line.startswith("---"):
                yaml_found = True
                continue
            if yaml_found and line.startswith("---"):
                yaml_end = line_num
                break

        yaml_block = "\n".join(file_lines[1:yaml_end])
        values = yaml.safe_load(yaml_block)

        if values is None:
            values = {}

        name = os.path.basename(filepath).replace(".md", '')
        values['name'] = name

        content = file_lines[yaml_end+1:]
        content = "\n".join(content)
        values['content'] = content

        # yaml.safe_load doesn't fully load the TextTableRelation type correctly
        # this fixes it and adds the target_table field back in
        for key, value in values.items():
            if type(value) is TextTableRelation:
                value.source_table = self
                value.target_table = self._properties[self._get_property_index(key)].target_table

        self.add_row(**values)

class TextDb:
    """a database system that uses plain system folders as the tables, markdown files as the rows, and a properties.yaml file as the defined properties (columns) for a table"""

    def __init__(self, name):
        self.name = name
        self._tables = []

        self.load()

    def __iter__(self):
        for item in self._tables:
            yield item

    def get_table(self, table_name):
        """get table by name"""

        table_names = [table.name for table in self._tables]
        if table_name not in table_names:
            raise ValueError(f"table {key} does not exist")
        return(self._tables[table_names.index(table_name)])
    def __getitem__(self, key):
        return self.get_table(key)
    def __getattr__(self, key):
        return self.get_table(key)

    def __repr__(self):
        return repr([table.name for table in self._tables])

    def resolve_path(self, obj=None):
        """resolves the path to the database, table or table row on the filesystem"""

        if obj is self or obj is None:
            return(self.name)
        elif type(obj) is TextTable:
            return(f"{format_name(self.name)}/{format_name(obj.name)}")
        elif type(obj) is TextTableRow:
            return(f"{format_name(self.name)}/{format_name(obj.parent.name)}/{format_name(obj.name)}.md")

    def add_table(self, table_name):
        """add a table into the database"""

        self._tables.append(TextTable(self, table_name))
    def add(self, table_name):
        """alias for add_table"""

        return self.add_table(table_name)
    def delete_table(self, table_name):
        """delete a table from the database"""

        for index, table in enumerate(self._tables):
            if table.name == table_name:
                del(self._tables[index])
                return
    def delete(self, table_name):
        """alias for delete_table"""

        return self.delete_table(table_name)

    def load(self):
        """load database contents from associated folder"""

        filepath = self.resolve_path(self)
        if not os.path.isdir(filepath):
            return False

        table_list = os.listdir(filepath)
        for table_name in table_list:
            if table_name[0] == '.': continue
            
            if os.path.isdir(f"{filepath}/{table_name}"):
                table = TextTable(self, table_name)
                table.load()

                self._tables.append(table)

        return self

    def save(self):
        """save database to the database folder"""

        required_dirs = [
            self.resolve_path(self),
            f"{self.resolve_path(self)}/.properties/"
        ]
        for required_dir in required_dirs:
            if not os.path.exists(required_dir):
                os.mkdir(required_dir)

        # if any tables have been deleted, delete them off the filesystem
        file_list = os.listdir(self.resolve_path(self))
        for table_name in file_list:
            if os.path.isdir(f"{self.name}/{table_name}"):
                if table_name == ".properties":
                    continue

                if table_name not in [table.name for table in self._tables]:
                    shutil.rmtree(f"{self.name}/{table_name}")
                    prop_file = f"{self.name}/.properties/{table_name}.yaml"
                    if os.path.isfile(prop_file):
                        os.remove(prop_file)

        for table in self._tables:
            if not os.path.exists(self.resolve_path(table)):
                os.mkdir(self.resolve_path(table))

            with open(f"{self.resolve_path(self)}/.properties/{table.name}.yaml", 'w') as f:
                properties_simple = {}
                for prop in table.get_properties():
                    properties_simple[prop.name] = prop.type_s

                f.write(yaml.dump(properties_simple))

            for row in table:
                with open(self.resolve_path(row), 'w') as f:
                    f.write(row.convert_to_markdown())

        return True

    def fix(self):
        """if the markdown files are edited by hand, this will update any properties"""
        self.load()
        self.save()
