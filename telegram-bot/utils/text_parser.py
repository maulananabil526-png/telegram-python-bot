import html

def escape_html(text):
    """Escape text untuk parse_mode HTML"""
    if not text:
        return ""
    return html.escape(str(text))

def safe_markdown_code(text):
    """Ensure markdown code blocks are properly closed"""
    if not text:
        return ""
    
    # Count backticks
    backtick_count = str(text).count('`')
    
    # If odd number of backticks, append one to close it
    if backtick_count % 2 != 0:
        return str(text) + '`'
    
    return str(text)
