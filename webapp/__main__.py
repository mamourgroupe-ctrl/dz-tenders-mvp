"""Allow ``python -m webapp`` as a shortcut for the CLI."""

from webapp.cli import main

raise SystemExit(main())
