import typer

from tasksquatch import __version__

app = typer.Typer(
    help="tasksquatch — offline-first todo tracker",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """
    tasksquatch — offline-first todo tracker.
    """


@app.command()
def version() -> None:
    typer.echo(__version__)
