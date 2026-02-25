from dataclasses import dataclass


@dataclass
class TimeProposalPayload:
    interviewer_tg_user_id: int
    student_tg_user_id: int
    interviewer_text: str
    student_text: str


def build_time_proposal_payload(
    interviewer_tg_user_id: int,
    student_tg_user_id: int,
    request_text: str,
    purpose_label: str,
    candidate_ref: str,
    interviewer_ref: str,
) -> TimeProposalPayload:
    interviewer_text = (
        "Новый запрос на собес 📩\n"
        f"Кандидат: {candidate_ref}\n"
        f"Назначение: {purpose_label}\n"
        f"Пожелания по времени: {request_text}\n\n"
        "Нажми кнопку и предложи финальный слот в формате YYYY-MM-DD HH:MM MSK"
    )
    student_text = (
        "Запрос отправлен интервьюеру ✅\n"
        f"Интервьюер: {interviewer_ref}\n"
        f"Назначение: {purpose_label}"
    )
    return TimeProposalPayload(
        interviewer_tg_user_id=interviewer_tg_user_id,
        student_tg_user_id=student_tg_user_id,
        interviewer_text=interviewer_text,
        student_text=student_text,
    )
