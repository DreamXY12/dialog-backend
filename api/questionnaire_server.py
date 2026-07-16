
from fastapi import APIRouter, Path, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# 你项目原生DB依赖
from sql.start import get_db

# ORM模型
from sql.people_models import Patient
from sql.people_models  import (
    PatientWeek9Questionnaire,
    QuestionnaireDMAnswer,
    QuestionnaireHTAnswer
)

# Pydantic结构
from sql.questionnaire_schema import (
    Week9QuestionnaireSubmit,
    QuestionnaireStatusResp,
    SingleQuestionnaireResp,
    QuizItem
)

router = APIRouter(prefix="/patients", tags=["第九周问卷管理"])
SessionDep = Depends(get_db)


# 1. 获取问卷弹窗状态（纯查询，无权限校验）
@router.get("/{patient_id}/week9-questionnaire-status", response_model=QuestionnaireStatusResp)
def get_week9_questionnaire_status(
        patient_id: int = Path(..., title="患者ID"),
        db: Session = SessionDep
):
    # 同时查询完成标记 + 账号创建时间
    stmt = select(
        Patient.is_week9_questionnaire_completed,
        Patient.create_time
    ).where(Patient.patient_id == patient_id)
    row = db.execute(stmt).one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="患者不存在")

    flag, create_time = row.tuple()
    return {
        "is_week9_questionnaire_completed": flag,
        "patient_create_time": create_time
    }


# 2. 提交/覆盖问卷（核心事务接口）
@router.post("/{patient_id}/week9-questionnaire")
def submit_week9_questionnaire(
    body: Week9QuestionnaireSubmit,
    patient_id: int = Path(...),
    db: Session = SessionDep
):
    try:
        # 查询是否已有问卷
        exist_q_stmt = select(PatientWeek9Questionnaire).where(PatientWeek9Questionnaire.patient_id == patient_id)
        exist_q = db.execute(exist_q_stmt).scalar_one_or_none()
        q_id = None

        if exist_q:
            # 更新旧问卷
            exist_q.assessment_date = body.baseHealth.assessmentDate
            exist_q.body_weight = body.baseHealth.bodyWeight
            exist_q.cardio_exercise_per_week = body.baseHealth.cardioExercisePerWeek
            exist_q.muscle_strengthen_per_week = body.baseHealth.muscleStrengthenPerWeek
            exist_q.alcohol_use = body.baseHealth.alcoholUse
            exist_q.smoking = body.baseHealth.smoking
            exist_q.healthy_diet_habit = body.baseHealth.healthyDietHabit
            exist_q.self_monitor_bp = body.baseHealth.selfMonitorBP
            exist_q.self_monitor_bg = body.baseHealth.selfMonitorBG
            exist_q.attempt_quit_smoking = body.baseHealth.attemptQuitSmoking
            exist_q.attempt_manage_weight = body.baseHealth.attemptManageWeight
            q_id = exist_q.id
        else:
            # 新建问卷
            new_q = PatientWeek9Questionnaire(
                patient_id=patient_id,
                assessment_date=body.baseHealth.assessmentDate,
                body_weight=body.baseHealth.bodyWeight,
                cardio_exercise_per_week=body.baseHealth.cardioExercisePerWeek,
                muscle_strengthen_per_week=body.baseHealth.muscleStrengthenPerWeek,
                alcohol_use=body.baseHealth.alcoholUse,
                smoking=body.baseHealth.smoking,
                healthy_diet_habit=body.baseHealth.healthyDietHabit,
                self_monitor_bp=body.baseHealth.selfMonitorBP,
                self_monitor_bg=body.baseHealth.selfMonitorBG,
                attempt_quit_smoking=body.baseHealth.attemptQuitSmoking,
                attempt_manage_weight=body.baseHealth.attemptManageWeight,
            )
            db.add(new_q)
            db.flush()
            q_id = new_q.id

        # 清空旧答题记录
        db.execute(delete(QuestionnaireDMAnswer).where(QuestionnaireDMAnswer.questionnaire_id == q_id))
        db.execute(delete(QuestionnaireHTAnswer).where(QuestionnaireHTAnswer.questionnaire_id == q_id))

        # 批量写入新答题
        dm_list = [
            QuestionnaireDMAnswer(questionnaire_id=q_id, question_id=item.questionId, answer=item.selectedAnswer)
            for item in body.dmQuiz
        ]
        ht_list = [
            QuestionnaireHTAnswer(questionnaire_id=q_id, question_id=item.questionId, answer=item.selectedAnswer)
            for item in body.htQuiz
        ]
        db.add_all(dm_list)
        db.add_all(ht_list)

        # 标记问卷已完成，前端永久关闭弹窗
        patient = db.execute(select(Patient).where(Patient.patient_id == patient_id)).scalar_one()
        patient.is_week9_questionnaire_completed = 1

        db.commit()
        return {"code": 200, "msg": "问卷提交成功", "questionnaire_id": q_id}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="问卷数据格式错误")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"提交失败: {str(e)}")


# 3. 查询已提交问卷（回填历史记录）
@router.get("/{patient_id}/week9-questionnaire", response_model=SingleQuestionnaireResp)
def get_patient_week9_questionnaire(
    patient_id: int = Path(...),
    db: Session = SessionDep
):
    q_main = db.execute(
        select(PatientWeek9Questionnaire).where(PatientWeek9Questionnaire.patient_id == patient_id)
    ).scalar_one_or_none()

    if not q_main:
        raise HTTPException(status_code=404, detail="暂无已提交问卷")

    # 获取答题明细
    dm_rows = db.execute(select(QuestionnaireDMAnswer).where(QuestionnaireDMAnswer.questionnaire_id == q_main.id)).scalars().all()
    ht_rows = db.execute(select(QuestionnaireHTAnswer).where(QuestionnaireHTAnswer.questionnaire_id == q_main.id)).scalars().all()

    dm_quiz = [QuizItem(questionId=r.question_id, selectedAnswer=r.answer) for r in dm_rows]
    ht_quiz = [QuizItem(questionId=r.question_id, selectedAnswer=r.answer) for r in ht_rows]

    return SingleQuestionnaireResp(
        id=q_main.id,
        patientId=q_main.patient_id,
        baseHealth={
            "assessmentDate": q_main.assessment_date,
            "bodyWeight": q_main.body_weight,
            "cardioExercisePerWeek": q_main.cardio_exercise_per_week,
            "muscleStrengthenPerWeek": q_main.muscle_strengthen_per_week,
            "alcoholUse": q_main.alcohol_use,
            "smoking": q_main.smoking,
            "healthyDietHabit": q_main.healthy_diet_habit,
            "selfMonitorBP": q_main.self_monitor_bp,
            "selfMonitorBG": q_main.self_monitor_bg,
            "attemptQuitSmoking": q_main.attempt_quit_smoking,
            "attemptManageWeight": q_main.attempt_manage_weight,
        },
        dmQuiz=dm_quiz,
        htQuiz=ht_quiz,
        createdAt=q_main.create_time.strftime("%Y-%m-%d %H:%M:%S"),
        updatedAt=q_main.update_time.strftime("%Y-%m-%d %H:%M:%S")
    )
