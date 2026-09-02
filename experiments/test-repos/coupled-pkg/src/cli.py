"""CLI module."""
import argparse


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command')

    analyze = sub.add_parser('analyze')
    analyze.add_argument('path', help='Path to analyze')

    args = parser.parse_args()
    if args.command == 'analyze':
        print(f'Analyzing {args.path}')


if __name__ == '__main__':
    main()
