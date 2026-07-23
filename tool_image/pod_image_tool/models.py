from dataclasses import dataclass


@dataclass
class ImageItem:
    filename: str
    name: str
    path: str
    size: int
    width: int
    height: int
    checked: bool = False

