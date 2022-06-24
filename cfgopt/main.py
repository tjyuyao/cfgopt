import argparse

import cfgopt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "recipe",
        help="a main function uri to be execute."
    )
    parser.add_argument(
        "-d", "--cfgdir",
        default="cfg",
        help="config directory that maps to cfg:// root. (default: `cfg`)"
    )
    args, unknown_args = parser.parse_known_args()
    cfgs = cfgopt.parse_configs(
        cfg_root=args.cfgdir,
        args=unknown_args,
        args_root=args.recipe,
    )
    _main = cfgs[args.recipe]
    return _main(recursive=False)


if __name__ == "__main__":
    main()
