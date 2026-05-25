"""Repositories — data access layer. Queries только; никакой бизнес-логики.

Каждый repo принимает AsyncSession в __init__ (через UnitOfWork), методы —
async, возвращают ORM-объекты или примитивы.
"""
