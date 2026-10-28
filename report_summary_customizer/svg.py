"""Validation and sanitization for user supplied inline SVG icons."""

import re
import xml.etree.ElementTree as ET
from html import escape
from typing import Any

import frappe
from frappe import _

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MAX_SVG_LENGTH = 50_000
MAX_SVG_NODES = 500
MAX_SVG_DEPTH = 20

ALLOWED_ELEMENTS = {"svg", "g", "path", "circle", "ellipse", "line", "polyline", "polygon", "rect"}
GEOMETRY_ELEMENTS = ALLOWED_ELEMENTS - {"svg", "g"}
ROOT_ATTRIBUTES = {
	"width",
	"height",
	"viewBox",
	"fill",
	"stroke",
	"stroke-width",
	"stroke-linecap",
	"stroke-linejoin",
	"stroke-dasharray",
	"stroke-dashoffset",
	"fill-rule",
	"clip-rule",
	"opacity",
}
GEOMETRY_ATTRIBUTES = {
	"d",
	"cx",
	"cy",
	"r",
	"rx",
	"ry",
	"x",
	"y",
	"x1",
	"y1",
	"x2",
	"y2",
	"width",
	"height",
	"points",
	"fill",
	"stroke",
	"stroke-width",
	"stroke-linecap",
	"stroke-linejoin",
	"stroke-dasharray",
	"stroke-dashoffset",
	"stroke-miterlimit",
	"fill-rule",
	"clip-rule",
	"opacity",
	"fill-opacity",
	"stroke-opacity",
	"transform",
}
GROUP_ATTRIBUTES = GEOMETRY_ATTRIBUTES - {
	"d",
	"cx",
	"cy",
	"r",
	"rx",
	"ry",
	"x",
	"y",
	"x1",
	"y1",
	"x2",
	"y2",
	"width",
	"height",
	"points",
}
NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:%|px|pt|pc|mm|cm|in|em|rem)?\Z")
NUMBER_LIST_PATTERN = re.compile(r"[-+0-9.eE,\s]+\Z")
PATH_PATTERN = re.compile(r"[-+0-9.eE,\sMmZzLlHhVvCcSsQqTtAa]+\Z")
COLOR_PATTERN = re.compile(r"(?:none|currentColor|[a-zA-Z]{1,20}|#[0-9a-fA-F]{3,8})\Z")
TRANSFORM_PATTERN = re.compile(
	r"\s*(?:(?:matrix|translate|scale|rotate|skewX|skewY)\s*\(\s*[-+0-9.eE,\s]+\)\s*)+\Z"
)


def sanitize_svg(value: str | None, label: str = "SVG Icon") -> str | None:
	"""Return a safe inline SVG containing only supported Lucide geometry."""
	if value is None:
		return None
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)

	markup = value.strip()
	if not markup:
		return None
	if len(markup) > MAX_SVG_LENGTH:
		frappe.throw(_("{0} must be no larger than 50 KB.").format(label), frappe.ValidationError)
	if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", markup, flags=re.IGNORECASE):
		frappe.throw(
			_("{0} cannot contain a document type or entity declaration.").format(label),
			frappe.ValidationError,
		)

	try:
		root = ET.fromstring(markup)
	except ET.ParseError:
		frappe.throw(_("{0} must be a complete, valid SVG element.").format(label), frappe.ValidationError)

	if _local_name(root.tag) != "svg" or _namespace(root.tag) not in {"", SVG_NAMESPACE}:
		frappe.throw(_("{0} must have an SVG root element.").format(label), frappe.ValidationError)

	state = {"count": 0, "geometry": 0}
	sanitized = _sanitize_element(root, label, state, 0, is_root=True)
	if state["geometry"] == 0:
		frappe.throw(_("{0} must include at least one drawable shape.").format(label), frappe.ValidationError)

	return _serialize_element(sanitized, is_root=True)


def _sanitize_element(
	element: ET.Element,
	label: str,
	state: dict[str, int],
	depth: int,
	*,
	is_root: bool = False,
) -> dict[str, Any]:
	state["count"] += 1
	name = _local_name(element.tag)
	if (
		state["count"] > MAX_SVG_NODES
		or depth > MAX_SVG_DEPTH
		or name not in ALLOWED_ELEMENTS
		or _namespace(element.tag) not in {"", SVG_NAMESPACE}
	):
		frappe.throw(
			_("{0} contains unsupported or overly complex SVG markup.").format(label), frappe.ValidationError
		)
	if not is_root and name == "svg":
		frappe.throw(_("{0} cannot contain nested SVG elements.").format(label), frappe.ValidationError)
	if element.text and element.text.strip():
		frappe.throw(_("{0} cannot contain text or embedded markup.").format(label), frappe.ValidationError)
	if name in GEOMETRY_ELEMENTS:
		state["geometry"] += 1
	if name not in {"svg", "g"} and len(element):
		frappe.throw(_("{0} contains invalid child elements.").format(label), frappe.ValidationError)

	allowed_attributes = (
		ROOT_ATTRIBUTES if is_root else GROUP_ATTRIBUTES if name == "g" else GEOMETRY_ATTRIBUTES
	)
	attributes = {}
	for raw_name, raw_value in element.attrib.items():
		attribute_name = _local_name(raw_name)
		if _namespace(raw_name) or attribute_name not in allowed_attributes:
			continue
		value = raw_value.strip()
		if not _is_safe_attribute(attribute_name, value):
			frappe.throw(
				_("{0} has an invalid SVG attribute: {1}.").format(label, attribute_name),
				frappe.ValidationError,
			)
		attributes[attribute_name] = value

	children = [
		_sanitize_element(child, label, state, depth + 1) for child in element if isinstance(child.tag, str)
	]
	return {"name": name, "attributes": attributes, "children": children}


def _is_safe_attribute(name: str, value: str) -> bool:
	if not value or len(value) > 20_000 or "url(" in value.lower() or "javascript:" in value.lower():
		return False
	if name in {"fill", "stroke"}:
		return bool(COLOR_PATTERN.fullmatch(value))
	if name in {"stroke-linecap"}:
		return value in {"butt", "round", "square"}
	if name in {"stroke-linejoin"}:
		return value in {"miter", "round", "bevel"}
	if name in {"fill-rule", "clip-rule"}:
		return value in {"nonzero", "evenodd"}
	if name == "viewBox":
		parts = re.split(r"[\s,]+", value)
		return len(parts) == 4 and all(NUMBER_PATTERN.fullmatch(part) for part in parts)
	if name in {"d"}:
		return bool(PATH_PATTERN.fullmatch(value))
	if name == "points":
		return bool(NUMBER_LIST_PATTERN.fullmatch(value))
	if name == "transform":
		return bool(TRANSFORM_PATTERN.fullmatch(value))
	if name == "stroke-dasharray":
		return value == "none" or bool(NUMBER_LIST_PATTERN.fullmatch(value))
	if name in {"opacity", "fill-opacity", "stroke-opacity"}:
		return bool(NUMBER_PATTERN.fullmatch(value))
	return bool(NUMBER_PATTERN.fullmatch(value))


def _serialize_element(element: dict[str, Any], *, is_root: bool = False) -> str:
	name = element["name"]
	attributes = dict(element["attributes"])
	if is_root:
		attributes = {"xmlns": SVG_NAMESPACE, **attributes}
	serialized_attributes = "".join(
		f' {key}="{escape(value, quote=True)}"' for key, value in attributes.items()
	)
	children = "".join(_serialize_element(child) for child in element["children"])
	if children:
		return f"<{name}{serialized_attributes}>{children}</{name}>"
	return f"<{name}{serialized_attributes}/>"


def _local_name(name: str) -> str:
	return name.rsplit("}", 1)[-1]


def _namespace(name: str) -> str:
	return name[1:].split("}", 1)[0] if name.startswith("{") else ""
