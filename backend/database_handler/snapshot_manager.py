from typing import Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json
import zlib

from .models import Snapshot, CurrentState, Transactions, TransactionStatus


class SnapshotManager:
    def __init__(self, session: Session):
        self.session = session

    def _compress_data(self, data: Dict) -> bytes:
        """Compress data using zlib and return as bytes."""
        json_data = json.dumps(data)
        return zlib.compress(json_data.encode())

    def _decompress_data(self, compressed_data: bytes) -> Dict:
        """Decompress bytes data back to dictionary."""
        if not compressed_data:
            return {}
        json_data = zlib.decompress(compressed_data)
        return json.loads(json_data)

    def create_snapshot(self) -> Snapshot:
        """Create a snapshot of the current state and transactions."""
        # Get all current states
        states = self.session.query(CurrentState).all()

        # Prepare state data for compression
        state_data = {
            state.id: {
                "data": state.data,
                "balance": state.balance,
                "updated_at": (
                    state.updated_at.isoformat() if state.updated_at else None
                ),
            }
            for state in states
        }

        transactions = self.session.query(Transactions).all()

        # Prepare transaction data for compression
        transaction_data = {
            tx.hash: {
                "status": tx.status.value,
                "from_address": tx.from_address,
                "to_address": tx.to_address,
                "input_data": tx.input_data,
                "data": tx.data,
                "consensus_data": tx.consensus_data,
                "nonce": tx.nonce,
                "value": tx.value,
                "type": tx.type,
                "gaslimit": tx.gaslimit,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "leader_only": tx.leader_only,
                "r": tx.r,
                "s": tx.s,
                "v": tx.v,
                "appeal_failed": tx.appeal_failed,
                "consensus_history": tx.consensus_history,
                "timestamp_appeal": tx.timestamp_appeal,
                "appeal_processing_time": tx.appeal_processing_time,
                "contract_snapshot": tx.contract_snapshot,
                "config_rotation_rounds": tx.config_rotation_rounds,
                "appealed": tx.appealed,
                "appeal_undetermined": tx.appeal_undetermined,
                "triggered_by_hash": tx.triggered_by_hash,
                "appealed": tx.appealed,
                "appeal_undetermined": tx.appeal_undetermined,
                "timestamp_awaiting_finalization": tx.timestamp_awaiting_finalization,
            }
            for tx in transactions
        }

        snapshot = Snapshot(
            state_data=self._compress_data(state_data),
            transaction_data=self._compress_data(transaction_data),
        )

        self.session.add(snapshot)
        self.session.commit()
        return snapshot

    def restore_snapshot(self, snapshot_id: int) -> bool:
        """Restore the database state from a snapshot."""
        try:
            # Get the snapshot
            snapshot = (
                self.session.query(Snapshot).filter_by(snapshot_id=snapshot_id).first()
            )
            if not snapshot:
                return False

            # Decompress the data with error handling
            try:
                state_data = self._decompress_data(snapshot.state_data)
                transaction_data = self._decompress_data(snapshot.transaction_data)
            except (zlib.error, json.JSONDecodeError) as e:
                raise ValueError(f"Failed to decompress snapshot data: {str(e)}")

            # Validate data structure
            if not isinstance(state_data, dict) or not isinstance(transaction_data, dict):
                raise ValueError("Invalid snapshot data structure")

            # Clear existing states and transactions
            self.session.query(CurrentState).delete()
            self.session.query(Transactions).delete()
            self.session.commit()

            # Restore current states
            for state_id, state_info in state_data.items():
                try:
                    new_state = CurrentState(
                        id=state_id,
                        data=state_info["data"],
                        balance=state_info["balance"]
                    )
                    if state_info.get("updated_at"):
                        try:
                            new_state.updated_at = datetime.fromisoformat(state_info["updated_at"])
                        except ValueError:
                            # Use current time if date is invalid
                            new_state.updated_at = datetime.now(datetime.UTC)
                    self.session.add(new_state)
                except KeyError as e:
                    raise ValueError(f"Missing required field in state data: {str(e)}")

            # Commit states before proceeding with transactions
            self.session.commit()

            # First pass: Create transactions
            transactions_map = {}  # Store transactions by hash for relationship setup
            for tx_hash, tx_info in transaction_data.items():
                try:
                    # Validate transaction status
                    try:
                        status = TransactionStatus(tx_info["status"])
                    except ValueError:
                        raise ValueError(f"Invalid transaction status: {tx_info['status']}")

                    new_tx = Transactions(
                        hash=tx_hash,
                        status=status,
                        from_address=tx_info["from_address"],
                        to_address=tx_info["to_address"],
                        input_data=tx_info["input_data"],
                        data=tx_info["data"],
                        consensus_data=tx_info["consensus_data"],
                        nonce=tx_info["nonce"],
                        value=tx_info["value"],
                        type=tx_info["type"],
                        gaslimit=tx_info["gaslimit"],
                        leader_only=tx_info["leader_only"],
                        r=tx_info["r"],
                        s=tx_info["s"],
                        v=tx_info["v"],
                        appeal_failed=tx_info["appeal_failed"],
                        consensus_history=tx_info["consensus_history"],
                        timestamp_appeal=tx_info["timestamp_appeal"],
                        appeal_processing_time=tx_info["appeal_processing_time"],
                        contract_snapshot=tx_info["contract_snapshot"],
                        config_rotation_rounds=tx_info["config_rotation_rounds"],
                        appealed=tx_info["appealed"],
                        appeal_undetermined=tx_info["appeal_undetermined"],
                        timestamp_awaiting_finalization=tx_info["timestamp_awaiting_finalization"],
                    )
                    if tx_info.get("created_at"):
                        try:
                            new_tx.created_at = datetime.fromisoformat(tx_info["created_at"])
                        except ValueError:
                            # Use current time if date is invalid
                            new_tx.created_at = datetime.now(datetime.UTC)
                    self.session.add(new_tx)
                    transactions_map[tx_hash] = new_tx
                except KeyError as e:
                    raise ValueError(f"Missing required field in transaction data: {str(e)}")

            # Commit first pass to get IDs
            self.session.commit()

            # Second pass: Set up relationships
            for tx_hash, tx_info in transaction_data.items():
                if tx_info.get("triggered_by_hash"):
                    triggered_hash = tx_info["triggered_by_hash"]
                    if triggered_hash not in transactions_map:
                        # Log warning and skip invalid relationship
                        print(f"Warning: Transaction {tx_hash} references non-existent transaction {triggered_hash}")
                        continue
                    tx = transactions_map[tx_hash]
                    tx.triggered_by_hash = triggered_hash

            # Commit relationship updates
            self.session.commit()
            return True

        except Exception as e:
            # Rollback on any error
            self.session.rollback()
            print(f"Error restoring snapshot: {str(e)}")
            return False

    def delete_all_snapshots(self) -> int:
        """Delete all snapshots from the database."""
        result = self.session.query(Snapshot).delete()
        self.session.commit()
        return result

    def get_snapshot(self, snapshot_id: int) -> Optional[Snapshot]:
        """Get a snapshot by its ID."""
        return self.session.query(Snapshot).filter_by(snapshot_id=snapshot_id).first()
