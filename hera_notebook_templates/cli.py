"""A CLI interface for running the notebooks using nbconvert."""

import click
from . import NOTEBOOKS
import jupyter_client
from pathlib import Path
import subprocess as sbp
import papermill as pm
import toml

NOTEBOOK_DICT = {nb.stem: nb for nb in NOTEBOOKS}

k_manager = jupyter_client.kernelspec.KernelSpecManager()
avail_kernels = k_manager.find_kernel_specs()

main = click.Group()

@main.command()
def avail():
    """List available notebooks."""
    for nb in NOTEBOOKS:
        click.echo(nb.stem)

@main.command()
@click.argument("notebook", type=click.Choice([nb.stem for nb in NOTEBOOKS]))
def inspect(notebook):
    infer = pm.inspect_notebook(str(NOTEBOOKS[[nb.stem for nb in NOTEBOOKS].index(notebook)]))

    print(f"Parameters available from {notebook}")
    print("---------------------------" + '-'*len(notebook))
    for p, v in infer.items():
        print(f"{p}: {v['inferred_type_name']}, default={v['default']}")
        print(f"   {v['help']}")

@main.group(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.option("-k", "--kernel", type=click.Choice(list(avail_kernels.keys())), default="python3")
@click.option("-f", "--formats", type=str, multiple=True, default=['html'])
@click.option("--ipynb/--no-ipynb", default=True)
@click.option("--output-dir", type=click.Path(exists=True, dir_okay=True, file_okay=False), default='.')
@click.option('--convert-args', type=str, default='')
@click.option("--toml", type=click.Path(exists=True, dir_okay=False, file_okay=True), default=None)
@click.option("--toml-section", type=str, default=None)
@click.pass_context
def run(ctx, kernel, formats, ipynb, output_dir, convert_args, toml, toml_section):
    """Use papermill to run a hera-templates notebook."""
    ctx.ensure_object(dict)

    ctx.obj['kernel'] = kernel
    ctx.obj['formats'] = formats
    ctx.obj['ipynb'] = ipynb
    ctx.obj['output_dir'] = output_dir
    ctx.obj['convert_args'] = convert_args
    ctx.obj['toml'] = toml
    ctx.obj['toml_section'] = toml_section

def run_notebook_factory(notebook):

    @click.option('-o', "--basename", type=str, default=None)
    @click.pass_context
    def runfunc(ctx, basename, **kwargs):
        nbfile = NOTEBOOK_DICT[notebook]

        if basename is None:
            basename = notebook
        
        output_path = Path(ctx.obj['output_dir']) / f"{basename}.ipynb"

        print("These are the input kwargs: ", kwargs)
        if ctx.obj['toml'] is not None:
            cfg = toml.load(ctx.obj['toml'])
            if ctx.obj['toml_section'] is not None:
                cfg = cfg[ctx.obj['toml_section']]
            kwargs.update(cfg)

        print(f"Executing Notebook and saving to {output_path}")
        print(f"Got notebook params: '{kwargs}'")
        
        kwargs['papermill_output_path'] = str(output_path)
        kwargs['papermill_input_path'] = str(nbfile)

        pm.execute_notebook(
            str(nbfile),
            output_path = output_path,
            kernel_name = ctx.obj['kernel'],
            parameters= kwargs,
        )

        for fmt in ctx.obj['formats']:
            print(f"Converting executed notebook to {fmt}...")
            sbp.run(
                [
                    'jupyter', 'nbconvert', 
                    "--output", f'{basename}.{fmt}',
                    "--output-dir", str(output_path.parent),
                    "--to", fmt,
                    ctx.obj['convert_args'],
                    str(output_path)
                ],
                check=True,
            )

        if not ctx.obj['ipynb']:
            output_path.unlink()

    infer = pm.inspect_notebook(str(NOTEBOOK_DICT[notebook]))
    tps = {
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        None: None,
        "Path": Path,
    }
    params = [
        click.option(
            f"--{param.replace('_', '-')}", 
            type=tps[v['inferred_type_name']], 
            default=eval(v['default']), 
            help=v['help'],
            show_default=True,
        ) if v['inferred_type_name'] != 'bool' else 
        click.option(
            f"--{param.replace('_', '-')}/--no-{param.replace('_', '-')}",  
            help=v['help'],
            default=eval(v['default'])
        )
        for param, v in infer.items()
    ]

    print("HERE ARE THE PARAMS BEFORE SETTING AS OPTIONS:", params)
    # Add all the parameters:
    for param in params:
        runfunc = param(runfunc)

    return click.command(name=notebook)(runfunc)


for nb in NOTEBOOK_DICT:
    run.add_command(run_notebook_factory(nb))