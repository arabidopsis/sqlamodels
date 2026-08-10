from __future__ import annotations

from types import ModuleType
from typing import IO

import click

from .cli import cli

EXPLAIN = """
This error might be due to the fact that the module imports more than
sqlalchemy. i.e. is not a simple generated output of `sqlamodels models` command.
Try installing `sqlamodels` in the same environment where the module is located and run this command again.
"""


@cli.command(name="schema")
@click.option(
    "-o",
    "--out",
    type=click.File("w"),
    default=None,
    help="Output file for generated schema code",
)
@click.option(
    "--no-singleton",
    is_flag=True,
    default=False,
    help="Do not create a singleton instances of the schema",
)
@click.option(
    "--module",
    "introspect_module",
    help="python module to introspect",
)
@click.option(
    "--exclude-classes",
    "exclude_classes",
    default="Base",
    help="Comma-separated list of classes to exclude. Defaults to 'Base'. See --module option for more details.",
)
@click.argument("model_classes", type=str, nargs=-1)
def schema_cmd(
    model_classes: tuple[str, ...],
    introspect_module: str | None,
    exclude_classes: str,
    out: IO[str] | None,
    no_singleton: bool = False,
) -> None:
    """Generate schema code for given SQLAlchemy model classes.

    Args:
        model_classes: Fully qualified names of the SQLAlchemy model classes
                       (e.g., 'anigozanthos.models.SequenceInventoryAll').
                       *OR* use the --module option to specify a module to introspect.
                       and just provide the class names (e.g., 'SequenceInventoryAll').
    """
    import sys
    from importlib import import_module

    from sqlalchemy.exc import NoInspectionAvailable
    from sqlalchemy.orm import DeclarativeBase

    from .mysqla import get_env
    from .schema import DynamicSchema

    if not model_classes and not introspect_module:
        click.secho(
            "Error: You must provide at least one model class or use the --module option.",
            err=True,
            fg="red",
        )
        raise click.Abort()

    exclude_classes_set = set(
        [c.strip() for c in exclude_classes.split(",") if c.strip()] if exclude_classes else [],
    )

    sys.path.insert(0, ".")  # Ensure current directory is in path

    def get_modules() -> list[tuple[str, type[DeclarativeBase]]]:
        ret = []
        mdict: dict[str, ModuleType] = {}
        for model_class in model_classes:
            # Dynamically import the model class
            if introspect_module:
                if "." in model_class:
                    click.secho(
                        f"Error: When using --module, model classes should not be fully qualified. Got: {model_class}",
                        err=True,
                        fg="red",
                    )
                    raise click.Abort
                module_name, class_name = introspect_module, model_class
            else:
                module_name, class_name = model_class.rsplit(".", 1)
            try:
                if module_name in mdict:
                    module = mdict[module_name]
                else:
                    module = import_module(module_name)
                    mdict[module_name] = module
            except ImportError as e:
                click.secho(
                    f"Error importing {module_name}: {e} ({EXPLAIN})",
                    err=True,
                    fg="red",
                )
                raise click.Abort
            model_cls = getattr(module, class_name, None)
            if model_cls is None:
                click.secho(
                    f"Error: {class_name} is not a valid class of module {module_name}",
                    err=True,
                    fg="red",
                )
                raise click.Abort
            if not isinstance(model_cls, type) or not issubclass(
                model_cls,
                DeclarativeBase,
            ):
                click.secho(
                    f"Error: {class_name} is not a subclass of DeclarativeBase in module {module_name}",
                    err=True,
                    fg="red",
                )
                raise click.Abort
            ret.append((class_name, model_cls))
        if not model_classes and introspect_module:
            ret.extend(get_modules2())
        return ret

    def get_modules2() -> list[tuple[str, type[DeclarativeBase]]]:
        ret = []
        assert introspect_module is not None
        try:
            module = import_module(introspect_module)
        except ImportError as e:
            click.secho(
                f"Error importing {introspect_module}: {e} ({EXPLAIN})",
                err=True,
                fg="red",
            )
            raise click.Abort()
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, DeclarativeBase)
                and obj != DeclarativeBase
                and (exclude_classes_set and name not in exclude_classes_set)
            ):
                ret.append((name, obj))
        return ret

    try:
        mods = get_modules()
        if not mods:
            click.secho(
                "Error: No valid model classes found.",
                err=True,
                fg="red",
            )
            raise click.Abort()
        schemas = [DynamicSchema.from_model(class_name, model_cls) for class_name, model_cls in mods]

        txt = (
            get_env()
            .get_template("meta.py.tmplt")
            .render(
                schemas=schemas,
                singleton=not no_singleton,
            )
        )
        if out is None:
            click.echo(txt)
            to = ""
        else:
            out.write(txt)
            to = f" to {out.name}" if out.name else ""
        click.secho(
            f'Schema code for "{", ".join(class_name for class_name, _ in mods)}" generated successfully{to}.',
            err=True,
            fg="green",
            bold=True,
        )
    except NoInspectionAvailable as e:
        click.secho(f"Error: {e}", err=True, fg="red")
        raise click.Abort()
