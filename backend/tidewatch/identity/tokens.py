"""Finding or creating tokens by their identity (chain + contract, or chain for a native coin).

Never by ticker: tickers are display-only (CLAUDE.md §4).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from tidewatch.db.models import Token


def native_token(session: Session, chain: str, name: str, ticker: str) -> Token:
    """The native coin of `chain`, created on first use."""
    token = session.scalars(
        select(Token).where(Token.chain == chain, Token.contract_address.is_(None))
    ).one_or_none()
    if token is None:
        token = Token(chain=chain, contract_address=None, name=name, ticker=ticker)
        session.add(token)
        session.flush()
    return token
