-----
10MAY26 Claude Code

- Created project documentation (CLAUDE.md) covering build commands, architecture, and key code patterns.
- Fixed map rendering — the mapping library version was mismatched with the satellite map layer, causing nothing to draw; pinned to the correct compatible version.
- Suppressed the browser right-click menu over the map so right-click-drag to tilt and rotate the view works cleanly.
- Added an MGRS grid coordinate field to the system editor — enter a grid reference and it updates the latitude/longitude automatically.
- Added a Watts field alongside the existing dBm power input; changing either one updates the other in real time.

-----
-----
10MAY26 Codex

- Added a visible map pin when a system is placed so users can see where it is right away.
- Made each pin stay visible on the map instead of only being obvious after selecting that system.
- Added drag-and-move behavior so users can reposition a placed system directly on the map.
- Kept the system details panel in sync so moving a pin also updates its saved coordinates.
- Improved the map interaction so selecting and moving systems is handled from the map itself.

-----
-----

10MAY26

- Initial commit based on Specter-EW
- Used Gemini to build the initial scaffold and code
- Experimenting with Claude Code and Codex for code creation
