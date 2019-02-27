import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from raiden.storage.sqlite import SQLiteStorage
from raiden.tests.utils.migrations import create_fake_web3_for_block_hash
from raiden.utils.upgrades import UpgradeManager


def setup_storage(db_path):
    storage = SQLiteStorage(str(db_path))

    # Add the v18 state changes to the DB
    state_changes_file = Path(__file__).parent / 'data/v18_statechanges.json'
    state_changes_data = json.loads(state_changes_file.read_text())
    for state_change_record in state_changes_data:
        storage.write_state_change(
            state_change=json.dumps(state_change_record[1]),
            log_time=datetime.utcnow().isoformat(timespec='milliseconds'),
        )

    # Add the v18 events to the DB
    events_file = Path(__file__).parent / 'data/v18_events.json'
    events_data = json.loads(events_file.read_text())
    for event in events_data:
        state_change_identifier = event[1]
        event_data = json.dumps(event[2])
        log_time = datetime.utcnow().isoformat(timespec='milliseconds')
        event_tuple = (
            None,
            state_change_identifier,
            log_time,
            event_data,
        )
        storage.write_events(
            state_change_identifier=state_change_identifier,
            events=[event_tuple],
            log_time=log_time,
        )

    # Finally add a chain state. Using the v17 already existing chainstate here out of laziness
    # and since for the purpose of the attributes of the chain state we migrate in v18->v19 it
    # should not mattter
    chain_state_data = Path(__file__).parent / 'data/v17_chainstate.json'
    chain_state = chain_state_data.read_text()
    cursor = storage.conn.cursor()
    cursor.execute(
        '''
        INSERT INTO state_snapshot(identifier, statechange_id, data)
        VALUES(1, 1, ?)
        ''', (chain_state,),
    )
    storage.conn.commit()

    return storage


def test_upgrade_v18_to_v19(tmp_path):
    db_path = tmp_path / Path('test.db')

    old_db_filename = tmp_path / Path('v18_log.db')
    with patch('raiden.utils.upgrades.older_db_file') as older_db_file:
        older_db_file.return_value = str(old_db_filename)
        storage = setup_storage(str(old_db_filename))
        with patch('raiden.storage.sqlite.RAIDEN_DB_VERSION', new=18):
            storage.update_version()
        storage.conn.close()

    web3, block_to_blockhash = create_fake_web3_for_block_hash(number_of_blocks=100)
    manager = UpgradeManager(db_filename=str(db_path), web3=web3)
    manager.run()

    storage = SQLiteStorage(str(db_path))
    # Check that all the relevant state changes now have the blockhash attribute
    state_change_records = storage.get_all_state_changes()
    for state_change_record in state_change_records:
        data = json.loads(state_change_record.data)
        affected_state_change = (
            'raiden.transfer.state_change.ContractReceive' in data['_type'] or
            'raiden.transfer.state_change.ActionInitChain' in data['_type']
        )
        if affected_state_change:
            assert 'block_hash' in data
            block_number = int(data['block_number'])
            assert block_to_blockhash[block_number].hex() == data['block_hash']

    # Check that all the relevant events now have the triggered_by_blockhash attribute
    event_records = storage.get_all_event_records()
    for event_record in event_records:
        data = json.loads(event_record.data)
        if 'events.ContractSend' in data['_type']:
            assert 'triggered_by_block_hash' in data

    # Finally check that the snapshot is updated and that it contains a blockhash and that all
    # pending transactions in the list also contain one
    _, snapshot = storage.get_latest_state_snapshot()
    snapshot_data = json.loads(snapshot)
    assert 'block_hash' in snapshot_data
    for transaction in snapshot_data['pending_transactions']:
        transaction_data = json.loads(transaction)
        assert 'triggered_by_blockhash' in transaction_data