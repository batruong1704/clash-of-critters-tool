"""In điểm khớp ảnh mẫu trên các ảnh có sẵn. Chạy: py -3 tools/score_templates.py"""

from gift_tool.paths import ROOT
from gift_tool.vision import Finder, avatar_point, field_point, imread

NAMES = ("search", "add", "visit", "gift", "close", "select", "ok")


def main():
    finder = Finder()
    print("templates")
    for name, (img, spec) in finder.templates.items():
        print(f"  {name}: {img.shape[1]}x{img.shape[0]} screen_w={spec['screen_w']} thr={spec['threshold']}")
    files = sorted(ROOT.glob("*.png")) + sorted((ROOT / "logs").glob("*.png"))
    for path in files:
        img = imread(path)
        height, width = img.shape[:2]
        print(f"\n{path.name} {width}x{height}")
        for key in NAMES:
            hit = finder.locate(img, key)
            mark = "OK" if hit.w and hit.score >= finder.templates[key][1]["threshold"] else "--"
            print(f"  {mark} {key:8} {hit.score:.3f} @ {hit.x},{hit.y} {hit.w}x{hit.h}")
        add = finder.find(img, "add")
        search = finder.find(img, "search")
        if add is not None:
            print("  avatar", avatar_point(img, add), "add", (add.x, add.y))
        if search is not None:
            print("  field", field_point(img, search), "search", (search.x, search.y))


if __name__ == "__main__":
    main()
