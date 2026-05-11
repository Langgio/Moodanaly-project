from apscheduler.schedulers.background import BackgroundScheduler

def generate_daily_reports():
    """每日凌晨執行，彙整前一日資料"""
    db = SessionLocal()
    yesterday = date.today()
    
    # 找出昨日有互動的所有長輩
    active_elders = db.query(Interaction.user_id).filter(
        Interaction.created_at >= yesterday
    ).distinct().all()

    for (elder_id,) in active_elders:
        interactions = db.query(Interaction).filter(
            Interaction.user_id == elder_id,
            Interaction.created_at >= yesterday
        ).all()
        
        # 統計情緒分布
        stats = {}
        for i in interactions:
            stats[i.emotion_label] = stats.get(i.emotion_label, 0) + 1
            
        summary = f"昨日長輩情緒穩定，共互動 {len(interactions)} 次，主要心情為 {max(stats, key=stats.get)}。"
        
        # 寫入日誌表
        log = CareLog(
            elder_id=elder_id,
            log_date=yesterday,
            summary=summary,
            emotion_metrics=stats
        )
        db.merge(log) # 使用 merge 防止重複寫入
    db.commit()
    db.close()

scheduler = BackgroundScheduler()
scheduler.add_job(generate_daily_reports, 'cron', hour=0, minute=5)
scheduler.start()