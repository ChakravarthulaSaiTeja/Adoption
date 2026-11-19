from marksapp.examnames import ExamName, suggest_exam_name

RULES = [["ADV", "Advance Exam"], ["MAIN", "Mains Exam"]]


def test_examples():
    assert suggest_exam_name("JEE(Adv)/WTA-4", RULES) == ExamName("Advance Exam", 4, "Advance Exam - 4", 0)
    assert suggest_exam_name("JEE(Main)/WTM-4", RULES) == ExamName("Mains Exam", 4, "Mains Exam - 4", 1)
    assert suggest_exam_name("JEE MAINS GT-12", RULES).number == 12
    assert suggest_exam_name("Weekly Test", RULES) == ExamName("Weekly Test", None, "Weekly Test", 2)
    assert suggest_exam_name(None, RULES) == ExamName("Exam", None, "Exam", 2)
