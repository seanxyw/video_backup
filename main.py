"""video-backup CLI

Commands:
    scan    <input_folder>            Workflow 1: scan & update timestamps
    split   <input_folder>            Workflow 2: copy to output/photos|youtube|unknown
    upload  <youtube_folder> [--title] Workflow 3: upload videos to YouTube
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
            print("Usage: python main.py scan <input_folder>")
            sys.exit(1)
        from scan import scan
        scan(sys.argv[2])

    elif command == "split":
        if len(sys.argv) < 3:
            print("Usage: python main.py split <input_folder>")
            sys.exit(1)
        from split import split
        split(sys.argv[2])

    elif command == "upload":
        if len(sys.argv) < 3:
            print("Usage: python main.py upload <youtube_folder> [--title <playlist_title>]")
            sys.exit(1)
        from upload import upload
        youtube_folder = sys.argv[2]
        title = None
        if "--title" in sys.argv:
            idx = sys.argv.index("--title")
            if idx + 1 < len(sys.argv):
                title = sys.argv[idx + 1]
        upload(youtube_folder, playlist_title=title)

    else:
        print(f"Unknown command: {command}")
        usage()


if __name__ == "__main__":
    main()
