import json

from logging import Logger
from pathlib import Path
from argparse import ArgumentParser

from .editor import Editor
from .edit_context import TimelineChange
from .utils.config import CfgID
from .utils.cli import cli_subcommand, FORMATTER_CLASS
from .processing.analysis import ANALYSIS_METHODS, ARG_PREPARE_ANALYSIS_METHOD_FN


@cli_subcommand
class CLI:
  COMMAND = 'direct'
  DESCRIPTION = 'Directs and produces summarized recordings'
  ARG_SRC = 'src'
  ARG_DST = 'dst'
  ARG_SUBS = 'subs'
  ARG_CONFIG = 'config'
  ARG_RECURSIVE = 'recursive'
  ARG_NO_EDIT = 'no_edit'
  ARG_METHOD = 'method'
  DEFAULT_ARGS = {ARG_SUBS: '', ARG_CONFIG: '', ARG_RECURSIVE: False, ARG_NO_EDIT: False}

  @staticmethod
  def setup_arg_parser(parser: ArgumentParser) -> ArgumentParser:
    """Sets up a CLI argument parser for this submodule

    Returns:
        ArgumentParser: Configured parser
    """
    parser.add_argument(CLI.ARG_SRC,
                        help='Path to the recording to summarize. If its a path to a directory, ' \
                          'every recording in the directory will be processed. Subtitle files ' \
                          'should then have the same name as their corresponding recordings',
                        type=str,
                        action='store')
    parser.add_argument(CLI.ARG_DST,
                        help='Directory for the summarized recordings',
                        type=str,
                        action='store')
    parser.add_argument('-s',
                        f'--{CLI.ARG_SUBS}',
                        help=f'Subtitle file. This is ignored when `{CLI.ARG_SRC}` is a directory',
                        type=str,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_SUBS])
    parser.add_argument('-c',
                        f'--{CLI.ARG_CONFIG}',
                        help='Configuration file defining the format of the output recordings',
                        type=str,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_CONFIG])
    parser.add_argument('-r',
                        f'--{CLI.ARG_RECURSIVE}',
                        help='Look recursively for recordings to summarize ' \
                          '(keeps folder structure)',
                        action='store_true',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_RECURSIVE])
    parser.add_argument('-n',
                        f'--{CLI.ARG_NO_EDIT}',
                        help='Instead of editing the recordings, only produces editing cfg files',
                        action='store_true',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_NO_EDIT])

    analysis_methods = parser.add_subparsers(title='Analysis methods',
                                             dest=CLI.ARG_METHOD,
                                             required=False)
    for method in ANALYSIS_METHODS:
      method.setup_arg_parser(
          analysis_methods.add_parser(method.COMMAND,
                                      help=method.DESCRIPTION,
                                      formatter_class=FORMATTER_CLASS))
    parser.set_defaults(run=CLI.run_submodule)
    return parser

  @staticmethod
  def run_submodule(args: object, logger: Logger) -> None:
    """Runs this submodule

    Args:
        args (object): Arguments of this submodule (defined in setup_arg_parser)
        logger (Logger): Logger for messages
    """
    args = args.__dict__
    src = Path(args[CLI.ARG_SRC]).resolve()
    dst = Path(args[CLI.ARG_DST]).resolve()
    subs = Path(args[CLI.ARG_SUBS]).resolve()
    cfg = Path(args[CLI.ARG_CONFIG]).resolve()
    no_edit = args[CLI.ARG_NO_EDIT]
    assert dst.is_dir()

    if src.is_file():
      dir_files = list(dst.glob('*'))
      dst_path = dst / src.name
      idx = 1
      while dst_path in dir_files:
        dst_path = dst / (src.stem + f' ({idx})' + src.suffix)
        idx += 1

      methods = []
      if cfg.is_file():
        with open(cfg, encoding='UTF-8') as cfg_file:
          cfg_dict = json.load(cfg_file)
        editor, _ = Editor.from_json(cfg_dict, logger)
        for method_idx, method_dict in enumerate(cfg_dict.get(CfgID.METHODS, [])):
          if len(method_dict) != 1:
            logger.warning(f'Bad {method_idx+1}. method structure, skipping')
            continue

          method_name, method_cfg_dict = list(method_dict.items())[0]
          for method in ANALYSIS_METHODS:
            if method.COMMAND == method_name:
              methods.append((method.prepare_method, method_cfg_dict))
              break
          else:
            logger.warning(f'Unrecognised analysis method: {method_name}')

      else:
        editor = Editor(logger=logger)

      if ARG_PREPARE_ANALYSIS_METHOD_FN in args:
        if len(methods) > 0:
          logger.warning('Analysis methods specified in the config file will be ignored')
        methods = [(args[ARG_PREPARE_ANALYSIS_METHOD_FN], args)]
      tl_changes = []
      for method_prepare_fn, method_cfg_dict in methods:
        method = method_prepare_fn(method_cfg_dict, logger=logger)
        new_tl_changes = method.analyze(str(src), str(subs) if subs.is_file() else None)
        tl_changes = TimelineChange.combine_changes(tl_changes, new_tl_changes)

      if no_edit:
        editor.export_json(dst / (dst_path.stem + '.json'), tl_changes)
      else:
        editor.edit(str(src), tl_changes, str(dst_path))
    elif src.is_dir():
      raise NotImplementedError()
    else:
      raise FileNotFoundError()
