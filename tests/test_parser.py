from parser import parse


def test_formats() -> None:
    eps = parse("EPISODE 8\n[00:01] A: Wait\nDoor opens\n00:03 Run\n"
                "# Ep 9\n1\n00:01:01,500 --> 00:01:05,000\nHello\n"
                "2\n00:01:06,000 --> 00:01:08,000\nBye")
    assert eps[8][0].text == "A: Wait Door opens"
    assert eps[8][0].end == 3
    assert eps[9][0].start == 61.5
    assert eps[9][-1].end == 68


def test_estimation() -> None:
    lines = parse("Episode 3\nHi\none two three four five")[3]
    assert [(l.idx, l.start, l.end, l.estimated) for l in lines] == [
        (0, 0, 1.5, True), (1, 1.5, 3.5, True)]


def test_native_simultaneous_action() -> None:
    source = """EPISODE NUMBER: Episode 5
EPISODE LOGLINE: Private context
**CAMERA:**
Start: (00:00.00) | End: (00:05.00)
A door opens.
**GUARD:**
Start: (00:00.00) | End: (00:03.00)
Stop!
**ACTION:**
Start: (00:03.00) | End: (00:05.00)
The door shuts.
--- SCRIPT END ---"""
    lines = parse(source)[5]
    assert len(lines) == 2 and lines[0].end == 3 and lines[1].end == 5
    assert lines[0].text == "CAMERA: A door opens. | GUARD: Stop!"
    assert not any(line.estimated for line in lines)


def test_hours_and_continuation() -> None:
    lines = parse("INT. HALL\n01:00:00 A key turns.\n01:00:25 Silence.")[1]
    assert lines[0].text == "INT. HALL A key turns."
    assert lines[0].start == 3600 and lines[0].end == 3625
