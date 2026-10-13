"""Sentence offsets shared by translation requests and the result window."""


def sentence_spans(text):
    spans = []
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        boundary = char in '。！？!?\n'
        if char == '.':
            boundary = not (index > 0 and index + 1 < len(text)
                            and text[index - 1].isdigit() and text[index + 1].isdigit())
        if boundary:
            end = index + 1
            while end < len(text) and text[end] in '。！？!?."”’\')':
                end += 1
            trimmed_start = start + len(text[start:end]) - len(text[start:end].lstrip())
            if trimmed_start < end:
                spans.append((trimmed_start, end))
            start = end
            index = end
        else:
            index += 1
    trimmed_start = start + len(text[start:]) - len(text[start:].lstrip())
    if trimmed_start < len(text):
        spans.append((trimmed_start, len(text)))
    return spans
