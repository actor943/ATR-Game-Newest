# -*- coding: utf-8 -*-
"""English (US).

键与 :mod:`core.locales.zh_CN` 一一对应；**缺哪个键就自动退回中文**，
所以没翻完也不会崩（跑 ``./venv/bin/python3 -m core.i18n`` 可以看缺哪些）。
"""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ---------------- common ----------------
    "common.back": "Back",
    "common.cancel": "Cancel",
    "common.coming_soon": "Coming soon",
    "common.on": "On",
    "common.off": "Off",

    # ---------------- core routes ----------------
    "route.home": "ATR Game",
    "route.single": "Single Player",
    "route.multiplayer": "Multiplayer",
    "route.room": "Room",
    "route.profile": "Me",
    "route.settings": "Settings",

    # ---------------- main menu ----------------
    "menu.settings": "Settings",
    "menu.me": "Me",
    "menu.no_nick": "No name yet",
    "menu.where": "Where to?",
    "menu.single": "Single Player",
    "menu.single_desc": "Play against the AI, or use the offline tools",
    "menu.multiplayer": "Multiplayer",
    "menu.multiplayer_desc": "Host a room on the same WiFi, with voice chat",
    "menu.footer": "v0.4.8 · LAN multiplayer",

    # ---------------- single player ----------------
    "single.title": "Single Player",
    "single.subtitle": "Pick one and play against the AI (or an offline tool).",
    "single.more": "More games",
    "single.more_desc": "Tiandao / Dou Dizhu / Paodekuai… coming soon.",

    # ---------------- profile ----------------
    "profile.title": "Me",
    "profile.subtitle": "This name is what other people see in a multiplayer "
                        "room.",
    "profile.current_nick": "Current name",
    "profile.nick_source": "Where it came from",
    "profile.nick_self": "You picked it",
    "profile.nick_random": "Randomly assigned (never changed)",
    "profile.change_nick": "Change name",
    "profile.random": "Random",
    "profile.save": "Save",
    "profile.empty_error": "The name cannot be empty",
    "profile.too_long": "16 characters at most",
    "profile.saved": "Saved: {nick}",
    "profile.rolled": "Rolled: {nick} (press Save to keep it)",
    "profile.tip": "If you join a room without a name, you get a random one "
                   "for the time being — change it here and everyone in the "
                   "room sees it right away.",

    # ---------------- settings ----------------
    "settings.title": "Settings",
    "settings.section_language": "Language",
    "settings.language_note": "Everything switches at once (menus, rooms, game "
                              "sub-menus…) — no restart needed.",
    "settings.section_pack": "Interface style",
    "settings.pack_note": "The whole app (Guandan table included) reskins at "
                          "once; community packs will show up here too.",
    "settings.pack_author": "by {author}",
    "settings.pack_community": " · community pack",
    "pack.default.name": "Default (Material)",
    "pack.default.desc": "A clean material look that follows light/dark; the "
                         "game screens use it too.",
    "pack.rustic.name": "Diablo II / MC (Stone)",
    "pack.rustic.desc": "Dungeon-hall look: beveled stone, dark gold trim and "
                        "torch dividers.",
    "settings.section_appearance": "Appearance",
    "settings.dark_theme": "Dark theme",
    "settings.theme_current": "Now: {mode}",
    "settings.theme_light": "Light",
    "settings.theme_dark": "Dark",
    "settings.dark_note": "Note: the Diablo / Minecraft stone pack is dark by "
                          "itself — this switch only matters for the default "
                          "style.",
    "settings.section_ui": "Interface",
    "settings.shortcut_hint": "Show shortcut hints",
    "settings.window_mode": "Window mode",
    "settings.data_dir": "Data folder: {path}",

    # ---------------- window modes ----------------
    "window.fullscreen": "Full screen (default)",
    "window.maximized": "Maximized",
    "window.windowed": "Windowed",

    # ---------------- multiplayer ----------------
    "mp.title": "Multiplayer",
    "mp.your_nick": "Your name: {nick}",
    "mp.tab_create": "Create a room",
    "mp.tab_search": "Find a room",
    "mp.room_name": "Room name",
    "mp.room_name_default": "{nick}'s room",
    "mp.room_code": "Room code",
    "mp.room_code_hint": "4~8 characters, your friends need it to get in",
    "mp.random": "Random",
    "mp.game": "Game",
    "mp.no_games": "(no playable game yet)",
    "mp.spectator_note": "Anyone beyond the seats this game needs watches "
                         "instead of playing.",
    "mp.seats": "Seats",
    "mp.seats_n": "{n} players",
    "mp.your_name": "Your name",
    "mp.your_name_hint": "What others see in the room; change it under \"Me\" "
                         "anytime",
    "mp.create_btn": "Create room",
    "mp.create_hint": "Once it's up, friends on the same WiFi / LAN see it "
                      "under \"Find a room\" — tell them the room code out "
                      "loud to let them in.",
    "mp.enter": "Enter",
    "mp.enter_room": "Enter room",
    "mp.unnamed_room": "(unnamed room)",
    "mp.room_meta": "{game} · host {host} · {ip}",
    "mp.scanning": "🧭 Looking for rooms on the local network…",
    "mp.scan_hint": "Have the host create the room first, and keep both "
                    "machines on the same WiFi / LAN.",
    "mp.code_dialog_title": "Enter {name}",
    "mp.code_dialog_hint": "Host: {host} · {game}",
    "mp.code_placeholder": "Room code (ask the host)",
    "mp.code_too_short": "The room code needs at least 4 characters",
    "mp.name_required": "Give the room a name first",
    "mp.create_failed": "Could not host: UDP port unavailable? (network "
                        "permission?)",
    "mp.join_failed": "Could not join: UDP port unavailable?",
    "mp.joining": "Joining \"{name}\"…",
    "mp.join_reject": "Refused: {reason}",
    "mp.no_response": "The host did not answer (room closed, or not on the "
                      "same LAN)",
    "mp.scan_busy": "Scan port already in use (a search is already running?)",
    "mp.no_room_yet": "No room yet: fill in the form above and press "
                      "\"Create room\".",

    # ---------------- room lobby ----------------
    "room.title": "Room",
    "room.empty": "There is no room here right now.",
    "room.back_mp": "Back to multiplayer",
    "room.room": "Room",
    "room.code": "Code {code}",
    "room.head_info": "Host {host} · {game} · {addr}",
    "room.head_hint": "Friends on the same WiFi / LAN can see this room under "
                      "\"Find a room\"; they need the room code to get in.",
    "room.seats": "Seats",
    "room.seats_hint": "Tap an empty seat to sit / switch; 🎤 = mic on, "
                       "🔇 = mic off, ♛ = host. Seats beyond what this game "
                       "needs are for spectators.",
    "room.empty_seat": "Seat {n}",
    "room.spectator": " · spectating",
    "room.spectator_paren": " (spectating)",
    "room.players_note": "{n} players on board",
    "room.players_note_extra": "{n} players on board, the rest spectate",
    "room.select_game": "Game (host can switch)",
    "room.current_game": "This game",
    "room.game_changed": "The host switched the game to {game}",
    "room.voice": "Voice",
    "room.mic_on": "Mic on",
    "room.mic_off": "Mic off",
    "room.speaker_on": "Speaker on",
    "room.speaker_off": "Speaker off",
    "room.level": "Level",
    "room.voice_tip": "Nothing is recorded by default — press \"Mic on\" to "
                      "start talking, and your friends' voice plays "
                      "automatically.",
    "room.voice_unavailable": "No audio library on this machine; install "
                              "sounddevice + numpy to talk.",
    "room.chat": "Chat",
    "room.chat_placeholder": "Say something…",
    "room.send": "Send",
    "room.start": "Start",
    "room.wait_start": "Waiting for start",
    "room.entered": "Joined \"{name}\" · {game}",
    "room.leave": "Left the room",
    "room.mic_enabled": "Microphone on",
    "room.mic_disabled": "Microphone off",
    "room.speaker_enabled": "Speaker on",
    "room.speaker_muted": "Speaker muted",
    "room.mic_error": "Could not open the microphone: check the system "
                      "permission, or another app may be holding the device.",
    "room.start_broadcast": "The host started the game — go!",
    "room.kicked": "The host removed you from the room",
    "room.game_not_ready": "\"{game}\" is not wired into the online room yet "
                           "— just gather everyone for now.",
    "room.game_failed": "The game screen failed to open (see the logs). "
                        "Stay in the room and try again.",

    # ---------------- networking ----------------
    "net.wrong_code": "Wrong room code",
    "net.no_response": "The host did not answer (network down?)",
    "net.already_started": "Already started",
    "net.room_full": "Room is full",
    "net.anon": "Nameless traveller",
    "net.wrong_code_sys": "Someone ({ip}) typed the wrong room code — refused",
    "net.joined": "{nick} joined the room",
    "net.left": "{nick} left the room",
    "net.dropped": "{nick} dropped out",
    "voice.port_error": "Could not open the voice port: {exc}",
    "voice.mic_error": "Could not open the microphone: {kind}: {exc}",
    "voice.speaker_error": "Could not open the speaker: {kind}: {exc}",

    # ---------------- history ----------------
    "history.refresh": "Refresh",
    "history.open_dir": "Open data folder",
    "history.section": "── full record ──",
    "history.log_dir": "Log folder: {path}",
    "history.log_dir_na": "Log folder: unavailable",
    "history.count": "{n} records",
    "history.none": "No records yet",
    "history.empty_body": "No records yet.\n\nA match is saved here "
                          "automatically once it ends — leaving halfway "
                          "leaves one behind too.",
    "history.empty_item": "(empty)",
    "history.empty_file": "(empty file)",
    "history.read_failed": "(could not read: {exc})",
    "history.open_failed": "Could not open the folder, go there manually:\n"
                           "{path}\n({exc})",
    "history.win_suffix": "{win} wins",
    "history.hands": "{n} rounds",

    # ---------------- game: Guandan ----------------
    "game.guandan.title": "Guandan",
    "game.guandan.desc": "Two decks, four players in two teams, climbing "
                         "through the ranks.",
    "guandan.choose_mode": "Pick a mode",
    "guandan.play": "Start a match",
    "guandan.play_desc": "Jump straight in with the last seats and room "
                         "setup: solo / three humans.",
    "guandan.board": "Card counter",
    "guandan.board_desc": "Log what has been played and see bomb odds from "
                          "all four seats.",
    "guandan.types": "Combo cheat sheet",
    "guandan.types_desc": "The usual combos and how they outrank each other.",
    "guandan.simulator": "Full simulation",
    "guandan.simulator_desc": "Watch four AIs play a whole match out, with "
                              "real card images.",
    "guandan.history": "History",
    "guandan.history_desc": "Look back at saved matches (auto-saved at the "
                            "end of each one).",
    "guandan.advisor": "AI advice",
    "guandan.advisor_desc": "Type in your hand and let the algorithm suggest "
                            "a play.",
    "guandan.advisor_heading": "AI advice mode",
    "guandan.advisor_body": "Type in your own hand: the algorithm looks at "
                            "what has been played and at your cards, then "
                            "suggests the best play.",
    "guandan.advisor_badge": "Ships in 0.5",
    "guandan.types_intro": "The combos below are the ones you see most in "
                           "Guandan. Bombs and the joker bomb ignore the "
                           "combo type — only the card count matters, then "
                           "the rank (2 is the lowest, A the highest).",
    "guandan.types_note": "Note: this tool only counts bombs of four or more "
                          "of a kind (wilds included) for now; straight "
                          "flushes and the rest arrive in 0.5.",
    "types.single": "Single",
    "types.single_desc": "Any one card",
    "types.pair": "Pair",
    "types.pair_desc": "Two cards of the same rank",
    "types.trio": "Trio",
    "types.trio_desc": "Three cards of the same rank",
    "types.full": "Full house",
    "types.full_desc": "A trio plus a pair",
    "types.straight": "Straight",
    "types.straight_desc": "5 or more consecutive ranks (2 does not join; "
                           "level cards can stand in for anything)",
    "types.flush": "Straight flush",
    "types.flush_desc": "A straight in one suit (the biggest normal combo in "
                        "Guandan)",
    "types.plate": "Steel plate",
    "types.plate_desc": "Two consecutive trios",
    "types.bomb4": "Bomb (4 cards)",
    "types.bomb4_desc": "Four of a kind, beats every combo above",
    "types.bomb5": "Bomb (5 cards)",
    "types.bomb5_desc": "Five of a kind, beats a 4-card bomb",
    "types.bomb6": "Bomb (6 cards)",
    "types.bomb6_desc": "Six of a kind, beats a 5-card bomb",
    "types.bomb7": "Bomb (7+ cards)",
    "types.bomb7_desc": "The more cards, the bigger it is",
    "types.jokers": "Joker bomb",
    "types.jokers_desc": "All four jokers from the two decks — the biggest "
                         "combo there is",

    # ---------------- game: Chess ----------------
    "game.chess.title": "Chess",
    "game.chess.desc": "Classic chess for two, with castling, en passant and "
                       "pawn promotion.",
    "chess.home.intro": "Local two-player (one side each): take turns on the "
                        "same device. Castling, en passant and promotion are "
                        "all supported.",
    "chess.home.play": "Start a game",
    "chess.home.play_desc": "Take turns locally, with undo / restart / skins",
    "chess.home.history": "History",
    "chess.home.history_desc": "Replay the moves of past games",

    # ---------------- placeholders ----------------
    "game.splendor.title": "Splendor",
    "game.splendor.desc": "Collect gems, buy development cards and race to 15 "
                          "prestige points.",
    "splendor.stub": "Splendor is in the works: gem collection, development "
                     "cards and prestige scoring are on the way.",
    "game.chinese_chess.title": "Chinese Chess",
    "game.chinese_chess.desc": "Xiangqi across the river and the palace — "
                               "the horse steps, the elephant flies.",
    "chinese_chess.stub": "Chinese Chess is in the works: board, move rules "
                          "and an AI opponent are on the way.",
}
