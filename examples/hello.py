from domonic.html import button, h1, main, p

from domonic_libs import App


app = App("Hello", width=600, height=400, debug=True)


def choose_file(event):
    paths = app.open_file(
        file_types=(
            "Text files (*.txt;*.md)",
            "All files (*.*)",
        )
    )

    print("Event:", event.type)
    print("Selected:", paths)


@app.route("/")
def index():
    return main(
        h1("Hello, world"),
        p("This interface was constructed with domonic."),
        button(
            "Choose file",
            _onclick=choose_file,
        )
    )


app.run()