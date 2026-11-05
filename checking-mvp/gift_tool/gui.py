"""Điểm vào cửa sổ. App là presenter của mô hình MVP."""

from gift_tool.presenter import Presenter


class App(Presenter):
    """Cửa sổ mà main và self-test dựng. Việc nằm ở Presenter, nét vẽ ở MainView, ADB ở ToolModel."""


def main():
    import tkinter as tk

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
