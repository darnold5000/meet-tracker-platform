#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Delete scores for athletes at The Flip Zone gym who have scores for The North Pole Classic meet.

This removes scores where:
- athlete.gym_id = 1 (The Flip Zone)
- score.meet_id = 1 (The North Pole Classic)
"""
import os
os.chdir('/Users/darnold_1/work/Generative AI Systems Architect/projects/06_usag_meet_tracker')
from dotenv import load_dotenv; load_dotenv('.env')
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from db.models import Score, Athlete

engine = create_engine(os.getenv('DATABASE_URL'))

# Query to find scores to delete
# Join scores -> athletes where gym_id=1 and meet_id=1
with Session(engine) as session:
    query = (
        session.query(Score)
        .join(Athlete)
        .filter(Athlete.gym_id == 1)  # The Flip Zone
        .filter(Score.meet_id == 1)  # The North Pole Classic
    )
    
    scores_to_delete = query.all()
    
    if not scores_to_delete:
        print("No scores found matching criteria.")
        exit(0)
    
    count = len(scores_to_delete)
    print("\nFound {} scores to delete:".format(count))
    for s in scores_to_delete:
        athlete = session.query(Athlete).filter(Athlete.id == s.athlete_id).one()
        print("  - Score ID {}: {} - {} - {:.3f} (Meet ID {})".format(
            s.id, athlete.canonical_name, s.event, s.score, s.meet_id
        ))
    
    confirm = input("\nWARNING: This will DELETE these scores!\nType 'DELETE' to confirm: ").strip()
    
    if confirm != 'DELETE':
        print("Cancelled. No scores deleted.")
        exit(0)
    
    print("\nDeleting scores...")
    
    deleted_count = 0
    with Session(engine) as session:
        query = (
            session.query(Score)
            .join(Athlete)
            .filter(Athlete.gym_id == 1)
            .filter(Score.meet_id == 1)
        )
        scores_to_delete = query.all()
        for score in scores_to_delete:
            session.delete(score)
            deleted_count += 1
        session.commit()
    
    print("\n✓ Deleted {} scores.".format(deleted_count))
    print("  All scores for Flip Zone athletes at The North Pole Classic have been removed.")
