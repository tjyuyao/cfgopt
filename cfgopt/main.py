import argparse

from .parser import parse_configs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "recipe",
        help="a main function uri to be execute."
    )
    parser.add_argument(
        "-d", "--cfgdir",
        default="cfg",
        help="config directory that maps to cfg:// root."
    )
    args, _ = parser.parse_known_args()
    cfgs = parse_configs(cfg_root=args.cfgdir)
    return cfgs[args.recipe]()


if __name__ == "__main__":
    main()
