import logging

def rule_based_sentiment(title):
    """簡單關鍵字新聞情緒標註"""
    pos_words = ["創高", "大漲", "利多", "突破", "買超", "雙增", "新高", "旺", "爆發", "成長", "合作", "獲利", "樂觀", "大單", "強勁", "擴產"]
    neg_words = ["大跌", "衰退", "利空", "大賣", "調降", "虧損", "倒貨", "走弱", "崩盤", "保守", "官司", "罰款", "暴跌", "下滑", "斷頭", "延後"]
    
    pos_cnt = sum(1 for w in pos_words if w in title)
    neg_cnt = sum(1 for w in neg_words if w in title)
    
    total = pos_cnt + neg_cnt
    if total == 0:
        return 0.00
    
    return round((pos_cnt - neg_cnt) / total * 0.8, 2)

# 全域快取 FinBERT 分類器，避免重複載入
_finbert_classifier = None

def get_finbert_sentiment(title):
    """利用 FinBERT-Chinese 模型對新聞標題進行情緒推理，支援無缝回退至關鍵字規則"""
    global _finbert_classifier
    try:
        if _finbert_classifier is None:
            from transformers import pipeline
            # 載入 FinBERT 中文情緒模型
            _finbert_classifier = pipeline("text-classification", model="yiyanghkust/finbert-tone-chinese")
        
        res = _finbert_classifier(title)[0]
        label = res['label'].upper()
        score = res['score']
        if 'POS' in label or 'LABEL_1' in label:
            return float(score)
        elif 'NEG' in label or 'LABEL_2' in label:
            return float(-score)
        else:
            return 0.0
    except Exception:
        # 若無法載入 transformers/PyTorch，或推理失敗，則回退到基於規則的情緒標註
        return rule_based_sentiment(title)
