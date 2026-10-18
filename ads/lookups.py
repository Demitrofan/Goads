"""Поиск по словам без учёта регистра для любых букв.

В SQLite «LIKE» и Django-шный icontains не различают регистр только у латиницы:
«Коляска» и «коляска» для них — разные слова. Поэтому в базу добавляется своя функция
py_lower (str.lower из Python знает все алфавиты), а поиск идёт через field__ucontains.
"""
from django.db.backends.signals import connection_created
from django.db.models import CharField, Lookup, TextField


def _lower(value):
    return value.lower() if isinstance(value, str) else value


def add_sqlite_lower(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.connection.create_function("py_lower", 1, _lower, deterministic=True)


class UContains(Lookup):
    lookup_name = "ucontains"

    def get_db_prep_lookup(self, value, connection):
        # «!» — знак экранирования: «100%» ищется как текст, а не как шаблон
        value = str(value).lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        return "%s", [f"%{value}%"]

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        fn = "py_lower" if connection.vendor == "sqlite" else "LOWER"
        return f"{fn}({lhs}) LIKE {rhs} ESCAPE '!'", [*lhs_params, *rhs_params]


def register():
    connection_created.connect(add_sqlite_lower)
    CharField.register_lookup(UContains)
    TextField.register_lookup(UContains)
