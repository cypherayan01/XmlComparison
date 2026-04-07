from lxml import etree


class XMLParseError(Exception):
    pass


def parse_xml_bytes(content: bytes) -> etree._Element:
    """
    Parse raw XML bytes into an lxml element tree.

    Uses a strict parser (no recovery) with huge_tree enabled for large files.
    Comments and processing instructions are stripped for clean comparison.

    Raises:
        XMLParseError: If the content is not well-formed XML.
    """
    try:
        parser = etree.XMLParser(
            remove_comments=True,
            remove_pis=True,
            recover=False,
            huge_tree=True,  # Allow files with 200k+ lines
        )
        root = etree.fromstring(content, parser=parser)
        return root
    except etree.XMLSyntaxError as exc:
        raise XMLParseError(f"Malformed XML: {exc}") from exc
