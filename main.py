"""video-backup CLI

Commands:
    scan    <input_folder> [--output-dir <path>]   Workflow 1: scan & update timestamps
    split   <folder_name>                           Workflow 2: copy to output dirs
    upload  <folder_name> [--title <title>]         Workflow 3: upload videos to YouTube
"""

import sys


def usage() -> None:
    print(__doc__)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2:
        usage()

    command = sys.argv[1]

    if command == "scan":
        if len(sys.argv) < 3:
            print("Usage: python main.py scan <input_folder> [--output-dir <path>]")
            sys.exit(1)
        from scan import scan
        output_dir = None
        if "--output-dir" in sys.argv:
            idx = sys.argv.index("--output-dir")
            if idx + 1 < len(sys.argv):
                output_dir = sys.argv[idx + 1]
        scan(sys.argv[2], output_dir=output_dir)

    elif command == "split":
        if len(sys.argv) < 3:
            print("Usage: python main.py split <folder_name>")
            sys.exit(1)
        from split import split
        split(sys.argv[2])

    elif command == "upload":
        if len(sys.argv) < 3:
            print("Usage: python main.py upload <folder_name> [--title <playlist_title>]")
            sys.exit(1)
        from upload import upload
        folder_name = sys.argv[2]
        title = None
        if "--title" in sys.argv:
            idx = sys.argv.index("--title")
            if idx + 1 < len(sys.argv):
                title = sys.argv[idx + 1]
        upload(folder_name, playlist_title=title)

    else:
        print(f"Unknown command: {command}")
        usage()


if __name__ == "__main__":
    main()
