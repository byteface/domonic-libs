from calendar import isleap
from datetime import date, datetime, timedelta

from domonic.events import Event
from domonic.html import (
    aside,
    button,
    div,
    h1,
    h2,
    header,
    input,
    label,
    main,
    p,
    section,
    span,
    style,
    textarea,
)

from domonic_libs import App


SETTINGS_FILE = "life-calendar-settings.json"
NOTES_FILE = "life-calendar-notes.json"
DEFAULT_LIFE_YEARS = 90

app = App("Life Calendar", width=1180, height=760, debug=False)

settings = app.load_json(SETTINGS_FILE, default={}) or {}
state = {
    "birthday": settings.get("birthday", ""),
    "birthday_draft": settings.get("birthday", ""),
    "life_years": int(settings.get("life_years", DEFAULT_LIFE_YEARS)),
    "life_years_draft": str(settings.get("life_years", DEFAULT_LIFE_YEARS)),
    "view": "life",
    "selected_year": date.today().year,
    "selected_day": date.today().isoformat(),
    "settings_open": not bool(settings.get("birthday")),
    "notes": app.load_json(NOTES_FILE, default={}) or {},
    "saved_at": "loaded",
}


def listen(node, event_type, callback):
    node.addEventListener(event_type, callback)
    return node


def save_settings():
    app.save_json(
        SETTINGS_FILE,
        {
            "birthday": state["birthday"],
            "life_years": state["life_years"],
        },
    )


def save_notes():
    state["notes"] = {
        day: note
        for day, note in state["notes"].items()
        if note.strip()
    }
    app.save_json(NOTES_FILE, state["notes"])
    state["saved_at"] = datetime.now().strftime("%H:%M:%S")


def birthday():
    if not state["birthday"]:
        return None

    try:
        return date.fromisoformat(state["birthday"])
    except ValueError:
        return None


def selected_day():
    return date.fromisoformat(state["selected_day"])


def years_lived():
    born = birthday()

    if born is None:
        return 0

    today = date.today()
    years = today.year - born.year

    if (today.month, today.day) < (born.month, born.day):
        years -= 1

    return max(0, years)


def days_lived():
    born = birthday()

    if born is None:
        return 0

    return max(0, (date.today() - born).days)


def lifespan_days():
    born = birthday()

    if born is None:
        return 0

    try:
        end = born.replace(year=born.year + state["life_years"])
    except ValueError:
        end = born.replace(month=2, day=28, year=born.year + state["life_years"])

    return max(1, (end - born).days)


def note_for(day):
    return state["notes"].get(day.isoformat(), "")


def year_note_count(year):
    prefix = f"{year}-"
    return sum(
        1
        for day, note in state["notes"].items()
        if day.startswith(prefix) and note.strip()
    )


def total_note_count():
    return sum(1 for note in state["notes"].values() if note.strip())


def year_start():
    born = birthday()
    return born.year if born else date.today().year


def year_end():
    return year_start() + state["life_years"]


def year_progress_class(year):
    today = date.today()

    if year < today.year:
        return "past"
    if year == today.year:
        return "current"
    return "future"


def day_for_index(year, index):
    return date(year, 1, 1) + timedelta(days=index)


def days_in_year(year):
    return 366 if isleap(year) else 365


def open_settings(event):
    state["birthday_draft"] = state["birthday"]
    state["life_years_draft"] = str(state["life_years"])
    state["settings_open"] = True


def close_settings(event):
    if state["birthday"]:
        state["settings_open"] = False


def update_birthday(event):
    state["birthday_draft"] = event.value or ""
    return False


def update_life_years(event):
    state["life_years_draft"] = event.value or str(DEFAULT_LIFE_YEARS)
    return False


def apply_settings(event):
    birthday_text = state["birthday_draft"]

    try:
        born = date.fromisoformat(birthday_text)
    except ValueError:
        state["birthday_draft"] = ""
        return

    try:
        life_years = int(state["life_years_draft"])
    except ValueError:
        life_years = DEFAULT_LIFE_YEARS

    life_years = min(130, max(1, life_years))
    state["birthday"] = born.isoformat()
    state["life_years"] = life_years
    state["life_years_draft"] = str(life_years)
    state["selected_year"] = min(max(date.today().year, born.year), year_end())
    state["selected_day"] = date.today().isoformat()
    state["settings_open"] = False
    state["view"] = "life"
    save_settings()


def select_year(event):
    year = int(
        getattr(event, "value", None)
        or getattr(getattr(event, "currentTarget", None), "value", None)
    )
    state["selected_year"] = year
    state["selected_day"] = date(year, 1, 1).isoformat()
    state["view"] = "year"


def show_life(event):
    state["view"] = "life"


def select_day(event):
    state["selected_day"] = (
        getattr(event, "value", None)
        or getattr(getattr(event, "currentTarget", None), "value", None)
        or state["selected_day"]
    )


def update_note(event):
    state["notes"][state["selected_day"]] = event.value or ""
    save_notes()
    return False


def clear_note(event):
    state["notes"].pop(state["selected_day"], None)
    save_notes()


def jump_today(event):
    today = date.today()
    state["selected_year"] = today.year
    state["selected_day"] = today.isoformat()
    state["view"] = "year"


def year_cell(year):
    classes = ["year", year_progress_class(year)]

    if year == state["selected_year"]:
        classes.append("selected")
    if year_note_count(year):
        classes.append("noted")

    node = button(
        span(str(year), _class="year-label"),
        span(f"{year_note_count(year)} notes", _class="year-notes"),
        _type="button",
        _value=str(year),
        _class=" ".join(classes),
    )
    return listen(node, Event.CLICK, select_year)


def day_cell(index):
    year = state["selected_year"]
    day = day_for_index(year, index)
    iso = day.isoformat()
    classes = ["day"]

    if iso == state["selected_day"]:
        classes.append("selected")
    if iso == date.today().isoformat():
        classes.append("today")
    if note_for(day).strip():
        classes.append("noted")

    node = button(
        span(str(day.day), _class="day-number"),
        span(day.strftime("%b"), _class="month"),
        _type="button",
        _value=iso,
        _class=" ".join(classes),
        **{"_data-day": iso},
    )
    return listen(node, Event.CLICK, select_day)


def base_styles():
    return style(
        """
        :root {
            color-scheme: light;
        }

        body {
            margin: 0;
            padding: 0;
            background: #f5f7f9;
            color: #20242a;
        }

        main {
            height: 100vh;
            display: grid;
            grid-template-columns: minmax(0, 1fr) 340px;
            overflow: hidden;
        }

        .content {
            min-width: 0;
            overflow: auto;
            padding: 26px;
            box-sizing: border-box;
        }

        header {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 20px;
            margin-bottom: 18px;
        }

        h1,
        h2,
        p {
            margin: 0;
        }

        h1 {
            font-size: 24px;
        }

        h2 {
            font-size: 18px;
        }

        .summary {
            color: #606b76;
            font-size: 14px;
            line-height: 1.4;
            margin-top: 4px;
        }

        .life-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
            gap: 8px;
        }

        .year {
            display: grid;
            align-content: center;
            gap: 3px;
            min-height: 58px;
            border: 1px solid #cbd3dc;
            border-radius: 6px;
            background: #ffffff;
            color: #20242a;
            cursor: pointer;
            padding: 8px;
            text-align: left;
        }

        .year.past {
            background: #dbe8df;
            border-color: #b9d1c0;
        }

        .year.current {
            border-color: #22577a;
            box-shadow: inset 0 0 0 2px rgba(34, 87, 122, 0.28);
        }

        .year.future {
            background: #ffffff;
        }

        .year.noted .year-notes {
            color: #2f855a;
            font-weight: 700;
        }

        .year.selected {
            background: #22577a;
            border-color: #22577a;
            color: white;
        }

        .year.selected .year-notes {
            color: white;
        }

        .year-label {
            font-size: 16px;
            font-weight: 800;
        }

        .year-notes {
            color: #606b76;
            font-size: 12px;
        }

        .day-grid {
            display: grid;
            grid-template-columns: repeat(53, minmax(10px, 1fr));
            gap: 4px;
        }

        .day {
            aspect-ratio: 1;
            min-width: 0;
            border: 1px solid #ccd4dd;
            border-radius: 3px;
            background: #ffffff;
            color: transparent;
            cursor: pointer;
            padding: 0;
        }

        .day:hover,
        .day.selected {
            border-color: #22577a;
            outline: 2px solid rgba(34, 87, 122, 0.18);
        }

        .day.today {
            background: #e7f1f5;
        }

        .day.noted {
            background: #2f855a;
            border-color: #2f855a;
        }

        .day.selected {
            background: #22577a;
        }

        .day-number,
        .month {
            display: none;
        }

        aside {
            height: 100vh;
            overflow: auto;
            border-left: 1px solid #d7dee6;
            background: #ffffff;
            padding: 24px;
            box-sizing: border-box;
        }

        .panel-date {
            display: grid;
            gap: 4px;
            margin-bottom: 16px;
        }

        .weekday {
            color: #606b76;
            font-size: 14px;
        }

        textarea,
        input {
            box-sizing: border-box;
            width: 100%;
            border: 1px solid #c6ced7;
            border-radius: 8px;
            background: #ffffff;
            color: #111827;
            caret-color: #111827;
            font: inherit;
        }

        textarea {
            min-height: 310px;
            padding: 12px;
            line-height: 1.45;
            resize: vertical;
        }

        input {
            min-height: 40px;
            padding: 8px 10px;
        }

        label {
            display: grid;
            gap: 6px;
            color: #374151;
            font-size: 13px;
            font-weight: 700;
        }

        .actions {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 12px;
        }

        button {
            min-height: 38px;
            border: 1px solid #22577a;
            border-radius: 6px;
            background: #22577a;
            color: white;
            cursor: pointer;
            font: inherit;
            font-weight: 700;
        }

        button.secondary {
            border-color: #c6ced7;
            background: #f4f7fa;
            color: #20242a;
        }

        .status {
            margin-top: 14px;
            color: #606b76;
            font-size: 13px;
            line-height: 1.45;
        }

        .modal-backdrop {
            position: fixed;
            inset: 0;
            display: grid;
            place-items: center;
            background: rgba(17, 24, 39, 0.45);
            padding: 20px;
            box-sizing: border-box;
        }

        .modal {
            width: min(100%, 420px);
            display: grid;
            gap: 14px;
            border-radius: 8px;
            background: #ffffff;
            padding: 22px;
            box-shadow: 0 20px 70px rgba(17, 24, 39, 0.28);
        }

        @media (max-width: 900px) {
            main {
                height: auto;
                min-height: 100vh;
                grid-template-columns: 1fr;
                overflow: visible;
            }

            aside {
                height: auto;
                border-left: 0;
                border-top: 1px solid #d7dee6;
            }

            .day-grid {
                grid-template-columns: repeat(26, minmax(10px, 1fr));
            }
        }
        """
    )


def life_view():
    born = birthday()
    lived = days_lived()
    total = lifespan_days()
    percent = int((lived / total) * 100) if total else 0

    return section(
        header(
            div(
                h1("Life calendar"),
                p(
                    (
                        f"Born {born.strftime('%d %B %Y')} · "
                        f"{years_lived()} years lived · "
                        f"{percent}% of {state['life_years']} years"
                    )
                    if born
                    else "Add your birthday to begin.",
                    _class="summary",
                ),
            ),
            div(
                listen(
                    button("Today", _type="button", _class="secondary"),
                    Event.CLICK,
                    jump_today,
                ),
                listen(
                    button("Settings", _type="button"),
                    Event.CLICK,
                    open_settings,
                ),
                _class="actions",
            ),
        ),
        div(
            *[year_cell(year) for year in range(year_start(), year_end())],
            _class="life-grid",
        ),
        _class="content",
    )


def year_view():
    year = state["selected_year"]
    return section(
        header(
            div(
                h1(str(year)),
                p(
                    f"{year_note_count(year)} noted days · "
                    f"{days_in_year(year)} days",
                    _class="summary",
                ),
            ),
            div(
                listen(
                    button("Life view", _type="button", _class="secondary"),
                    Event.CLICK,
                    show_life,
                ),
                listen(
                    button("Settings", _type="button"),
                    Event.CLICK,
                    open_settings,
                ),
                _class="actions",
            ),
        ),
        div(
            *[day_cell(i) for i in range(days_in_year(year))],
            _class="day-grid",
        ),
        _class="content",
    )


def notes_panel():
    day = selected_day()
    note_area = listen(
        textarea(
            note_for(day),
            _name="note",
            _placeholder="Write a note for this day",
            _autocomplete="off",
            _autocorrect="off",
            _spellcheck="false",
        ),
        Event.INPUT,
        update_note,
    )

    return aside(
        div(
            h2(day.strftime("%d %B %Y")),
            span(day.strftime("%A"), _class="weekday"),
            _class="panel-date",
        ),
        note_area,
        div(
            listen(
                button("Clear note", _type="button", _class="secondary"),
                Event.CLICK,
                clear_note,
            ),
            listen(
                button("Today", _type="button"),
                Event.CLICK,
                jump_today,
            ),
            _class="actions",
        ),
        p(
            f"{total_note_count()} saved notes · saved {state['saved_at']}",
            _class="status",
        ),
        p(f"Data: {app.data_path(NOTES_FILE)}", _class="status"),
    )


def settings_modal():
    if not state["settings_open"]:
        return ""

    birthday_input = listen(
        input(
            _type="date",
            _name="birthday",
            _value=state["birthday_draft"],
            _autocomplete="off",
        ),
        Event.INPUT,
        update_birthday,
    )
    years_input = listen(
        input(
            _type="number",
            _name="life_years",
            _value=state["life_years_draft"],
            _min="1",
            _max="130",
            _autocomplete="off",
        ),
        Event.INPUT,
        update_life_years,
    )
    save_button = listen(
        button("Save settings", _type="button"),
        Event.CLICK,
        apply_settings,
    )
    close_button = listen(
        button("Cancel", _type="button", _class="secondary"),
        Event.CLICK,
        close_settings,
    )

    return div(
        div(
            h2("Settings"),
            p(
                "Enter your birthday to build the full life view.",
                _class="summary",
            ),
            label("Birthday", birthday_input),
            label("Life expectancy in years", years_input),
            div(save_button, close_button, _class="actions"),
            _class="modal",
        ),
        _class="modal-backdrop",
    )


@app.route("/")
def index():
    view = life_view() if state["view"] == "life" else year_view()

    return main(
        base_styles(),
        view,
        notes_panel(),
        settings_modal(),
    )


app.run()
