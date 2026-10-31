"""음성(문장) 명령: 문장 → 의도 → 투과 단계.

- text.py    : 문장 정리, 글자 n-gram, 단계 숫자 뽑기 (학습과 Pi 추론이 같은 함수를 쓴다)
- intent.py  : 의도 분류기 추론 (Pi, 인터넷 없이). 모델은 pi/data/intent_model.json
- train.py   : 의도 분류기 학습 (노트북, scikit-learn 필요)
- llm.py     : 분류기가 확신하지 못한 문장만 LLM(Gemini)에 묻는다. 키가 없으면 꺼짐
- handler.py : 의도를 실제 동작(단계 변경, 자동 모드, 상태 응답)으로 바꾼다
"""
