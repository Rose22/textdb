import os
import shutil
import yaml
import datetime
import debug

# TODO: add in proper support for types with extra data, such as relations
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

class CustomType(dict):
    # hopefully a way to handle yaml conversion of custom types such as relations and selects
    def __init__(self, core_type, structure : dict):
        self.type = core_type
        self.structure = structure

    def __call__(self):
        return self.type()

class TextTablePropertyType:
    """
    table property type. takes a string and converts it to an internal python type
    ex: "text" becomes str()

    supports custom types, which consist of a core type (what table cols store the value as), and a structure
    a custom type example would be:
    options = ['unfinished', 'in progress', 'done']
    status = CustomType(str, {"options": options})

    custom types are mainly meant to help save these weird types in the yaml files. it's up to the UI to interpret how to display these types and what to do with them.

    a UI would take this custom type, and present it as a list of selecteable options, storing the selected option as a string inside the table column. you could also use an int for this.

    it's made to be easily extensible by just adding more custom types to the typemap
    """
    typemap = {
        "text": str,
        "number": float,
        "datetime": datetime.datetime,
        "date": datetime.date,
        "time": datetime.time,
        "checkbox": bool,
        "select": CustomType(int, {"options": []}),
        "relation": CustomType(list, {"target": str()}),
        "multiselect": CustomType(list, {"options": []})
    }

    # draft
    extra_data = {
        "select": {"options": str},
        "relation": {"target_table": list}
    }

    def __init__(self, type_string : str, structure : dict = None):
        if type_string not in self.typemap.keys():
            raise ValueError(f"{type_string} is not a valid type. valid types: {', '.join(list(self.typemap.keys()))}")

        self.name = type_string

        # contains the python type class itself, not an instance. for example, str. it can be called (as self.object()) to create an instance of that python type. it would be the same as calling str()
        self.object = self.typemap[type_string] 

        self.is_custom = False
        if isinstance(self.object, CustomType):
            self.is_custom = True

    def convert(self, value):
        converted = None

        if value.lower() == "false":
            converted = False
        elif value.lower() == "true":
            converted = True
        elif value.isnumeric():
            converted = float(value)

        return converted

    @property
    def default_value(self):
        return self.object()

    @property
    def structure(self):
        """makes custom type structures accessible from the type level instead of having to go into the type object"""

        if self.is_custom:
            return self.object.structure
        return None

class TextTableProperty:
    """table property. simply just a set of a name and a TextTablePropertyType"""

    def __init__(self, property_name : str, property_type : str, structure : dict = None):
        self.name = property_name
        self.type = TextTablePropertyType(property_type)

        if structure and self.type.is_custom:
            self.type.object.structure = structure

class TextTableCols(dict):
    """special dict that auto formats the name"""

    def __setitem__(self, key, value):
        if key == "name":
            value = format_name(value)

        return dict.__setitem__(self, key, value)

class TextTableRow:
    def __init__(self, parent_table, name):
        # cols (columns) are basically dicts of simple key-value pairs
        # a col looks like:
        # {"name": "my row", "content": "blahblahblah", "checked": True}
        # and so on
        # the typemapping and type verification gets handled by TextTable, because why would i store the type of a col for every row in the table?
        self.cols = TextTableCols()

        self.parent = parent_table

    def __repr__(self):
        return repr(self.cols)

    def __getattr__(self, key):
        """l                                the links
ets you access row columns as if they are class properties"""
        return self.cols.__getitem__(key)
    def __getitem__(self, key):
        """lets you access row columns as if they are dict keys"""
        return self.cols.__getitem__(key)

    def __iter__(self):
        """lets you iterate through the object which will just iterate through its stored cols"""

        for key, value in self.cols.items():
            yield (key, value)

    def keys(self):
        return self.cols.keys()

    def resolve_path(self):
        return self.parent.parent.resolve_path(self)

    def convert_to_markdown(self):
        if self.cols and self.cols.keys() != TextTable.protected_properties:
            dump_cols = dict(self.cols)
            for key in TextTable.protected_properties:
                del(dump_cols[key])

            return(f"---\n{yaml.safe_dump(dump_cols)}---\n{self.cols['content']}")
        else:
            return(self.content)

class TextTable:
    protected_properties = ("name", "content")

    def __init__(self, parent_db, name):
        self.parent = parent_db

        self.name = name

        # each property has a name and a type
        self._properties = []
        # name is a special property that cannot be altered or removed, because it is used as the filename. make sure we format it to a name that can be used on the filesystem.
        self._properties.append(TextTableProperty("name", "text"))
        # also a special property that contains the content below all the user-defined properties. this must not be removed because it represents the content portion of a saved markdown file (below the yaml --- block)
        self._properties.append(TextTableProperty("content", "text"))

        # each row has cols that are defined by the table's properties. cols contain the property name and the col value
        self._rows = []

    def __iter__(self):
        """lets you use for loops on the table object itself to loop through rows"""

        for row in self._rows:
            yield row
    def __getitem__(self, key):
        """lets you get rows by name like table['examplerow']"""

        return self.get(key)
    def __getattr__(self, key):
        """lets you get rows by name like table.examplerow"""

        return self.get(key)

    def __repr__(self):
        names = []
        for row in self:
            names.append(f"'{row.cols['name']}'")

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

    def add_property(self, property_name, property_type, structure=None):
        """add a property to the table"""

        # don't allow editing protected properties
        if property_name in self.protected_properties:
            return False

        self._properties.append(TextTableProperty(property_name, property_type, structure))
        self._update_rows()
    def edit_property(self, property_name, **kwargs):
        """edit an existing property. use keyword arguments to specify what to edit"""

        # don't allow editing protected properties
        if property_name in self.protected_properties:
            return False

        prop = self.get_property(property_name)
        if not prop:
            return False

        if "name" in kwargs.keys():
            prop.name = kwargs['name']
        if "type" in kwargs.keys():
            prop.type = kwargs['type']

        # rename the property across all rows, preserving property order
        for row in self._rows:
            new_cols = {}
            for prop_name in row.cols.keys():
                if prop_name == property_name:
                    prop_name = kwargs['name']

                new_cols[prop_name] = row.cols[property_name]

            row.cols = new_cols
    def del_property(self, property_name):
        """delete a property from the table"""

        # don't allow deleting protected properties
        if property_name in self.protected_properties:
            return False

        del(self._properties[self._get_property_index(property_name)])
        self._update_rows()

    def _update_rows(self):
        """update rows to make sure everything reflects the table structure"""

        for row in self._rows:
            add_queue = []
            delete_queue = []

            for property_name in row.cols.keys():
                if property_name not in self.get_property_names():
                    delete_queue.append(property_name)
            for property_name in self.get_property_names():
                if property_name not in row.cols.keys():
                    add_queue.append(property_name)

            for property_name in delete_queue:
                del(row.cols[property_name])
            for property_name in add_queue:
                prop = self.get_property(property_name)

                row.cols[property_name] = prop.type.default_value

    def add_row(self, *args, **kwargs):
        """add a row to the table. use keyword arguments to specify what values you want to add into the table's properties"""

        if len(args) > 0 and len(kwargs) == 0:
            kwargs = {}
            prop_names = self.get_property_names()

            for index, arg in enumerate(args):
                kwargs[prop_names[index]] = arg
        elif len(args) == 1 and len(kwargs) > 0:
            kwargs = {"name": args[0]} | kwargs

        if "name" not in kwargs.keys():
            raise ValueError("missing name argument")

        # ensure no duplicate rows allowed
        for row in self._rows:
            if row['name'] == format_name(kwargs['name']):
                return False

        row = TextTableRow(self, kwargs['name'])

        # predefine all the row columns regardless of content
        for prop in self._properties:
            row.cols[prop.name] = prop.type.default_value

        # load the kwargs into the cols of the new row
        for prop_name, value in kwargs.items():
            if prop_name not in self.get_property_names():
                continue

            prop = self.get_property(prop_name)

            if not prop:
                raise ValueError(f"property {prop_name} does not exist")

            if type(value) != prop.type.object: 
                if type(value) is str:
                    value = prop.type.convert(value)
                elif prop.type.is_custom:
                    value = value
                elif value is None:
                    pass
                else:
                    raise TypeError(f"{prop.name} should be of type {prop.type}, but is {type(value)}") 

            row.cols[prop_name] = value

        self._rows.append(row)
    def add(self, *args, **kwargs):
        """alias for add_row"""

        return self.add_row(*args, **kwargs)

    def _get_row_index(self, *args):
        """
        get the index of a row. used internally by the class
        you can either get it by name, or get it by a specified property
        """

        # when there's 1 argument, use the name as the target property. else, use arg 1 as the target property, arg 2 as the target value
        if len(args) > 1:
            target_property = args[0]
            target_value = args[1]
        else:
            target_property = "name"
            target_value = args[0]

        for index, row in enumerate(self._rows):
            if row.cols[target_property] == target_value:
                return index

        return None
    def get_row(self, args):
        """fetch a row object using _get_row_index()"""

        index = self._get_row_index(args)
        if index is None:
            return None

        return self._rows[index]
    def get(self, *args):
        """alias for get_row"""

        return self.get_row(*args)

    def edit_row(self, row_name, **kwargs):
        """edit a row. use keyword arguments to specify what to edit"""

        row = self.get_row(row_name)
        if row is None:
            raise IndexError(f"row {row_name} not found")
        
        for prop_name, prop_value in kwargs.items():
            if prop_name == "content":
                row.content = prop_value.strip()
                continue

            if prop_name in row.cols.keys():
                row.cols[prop_name] = prop_value
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
        """load the table with all appropriate data according to the stored paths"""

        self.load_properties()

        filelist = os.listdir(self.resolve_path())
        for filename in filelist:
            filepath = f"{self.resolve_path()}/{filename}"
            self.load_row_file(filepath)

        return self

    def load_properties(self):
        """load table properties from the appropriate yaml file"""

        filepath = f"{self.parent.resolve_path()}/.properties/{self.name}.yaml"

        if not os.path.isfile(filepath):
            return False

        with open(filepath, 'r') as f:
           file = f.read()

        if not file:
            return False

        loaded_properties = yaml.safe_load(file)

        for key, value in loaded_properties.items():
            # custom type
            type_name = value
            structure = None

            if isinstance(value, dict):
                type_name = value['type']
                structure = value['structure']

            self.add_property(key, type_name, structure)

    def load_row_file(self, filepath):
        """load row from a markdown file"""

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

        self.add_row(**values)

class TextDb:
    """a database system that uses plain system folders as the tables, markdown files as the rows, and a properties.yaml file as the defined properties (columns) for a table"""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(self.path)
        self._tables = []

        self.load()

    def __iter__(self):
        for item in self._tables:
            yield item

    def get_table_names(self):
        return [table.name for table in self._tables]
    def get_table(self, table_name):
        """get table by name"""

        table_names = self.get_table_names()
        if table_name not in table_names:
            return None

        return(self._tables[table_names.index(table_name)])

    def __getitem__(self, key):
        return self.get_table(key)
    def __getattr__(self, key):
        return self.get_table(key)

    def __repr__(self):
        return repr([table.name for table in self._tables])
        
    def get_types(self):
        return TextTablePropertyType.typemap

    def resolve_path(self, obj=None):
        """resolves the path to the database, table or table row on the filesystem"""

        if obj is self or obj is None:
            return(self.path)
        elif type(obj) is TextTable:
            return(f"{self.path}/{format_name(obj.name)}")
        elif type(obj) is TextTableRow:
            return(f"{self.path}/{format_name(obj.parent.name)}/{format_name(obj.name)}.md")

    def add_table(self, table_name):
        """add a table into the database"""

        self._tables.append(TextTable(self, table_name))

    def delete_table(self, table_name):
        """delete a table from the database"""

        for index, table in enumerate(self._tables):
            if table.name == table_name:
                del(self._tables[index])
                return

    def load(self):
        """load database contents from associated folder"""
        
        # start with a blank slate
        self._tables = []

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
        # likewise for table rows
        file_list = os.listdir(self.resolve_path(self))
        for folder_name in file_list:
            if os.path.isdir(f"{self.path}/{folder_name}"):
                if folder_name == ".properties":
                    continue

                if folder_name not in self.get_table_names():
                    shutil.rmtree(f"{self.path}/{folder_name}")
                    prop_file = f"{self.path}/.properties/{folder_name}.yaml"
                    if os.path.isfile(prop_file):
                        os.remove(prop_file)

                row_names = []
                for row in self.get_table(folder_name):
                    row_names.append(row.cols['name'])

                for row_filename in os.listdir(f"{self.path}/{folder_name}"):
                    row_name = os.path.splitext(row_filename)[0]
                    if row_name not in row_names:
                        os.remove(f"{self.path}/{folder_name}/{row_filename}")

        for table in self._tables:
            if not os.path.exists(self.resolve_path(table)):
                os.mkdir(self.resolve_path(table))

            with open(f"{self.resolve_path(self)}/.properties/{table.name}.yaml", 'w') as f:
                properties_simple = {}
                for prop in table.get_properties():
                    # custom type support
                    if prop.type.is_custom:
                        properties_simple[prop.name] = {"type": prop.type.name, "structure": prop.type.object.structure}
                    else:
                        properties_simple[prop.name] = prop.type.name

                f.write(yaml.dump(properties_simple))

            for row in table:
                with open(self.resolve_path(row), 'w') as f:
                    f.write(row.convert_to_markdown())

        return True

    def reload(self):
        """if the markdown files are edited by hand, this will update any properties"""

        self.load()
        self.save()

    def get(self, *args):
        """alias for get_table"""
        return self.get_table(*args)
    def add(self, table_name):
        """alias for add_table"""
        return self.add_table(table_name)
    def delete(self, table_name):
        """alias for delete_table"""

        return self.delete_table(table_name)
