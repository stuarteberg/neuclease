import pytest
import requests
import numpy as np

from neuclease.merge_graph import LabelmapMergeGraph
from neuclease.merge_table import load_merge_table

##
## These tests rely on the global setupfunction 'labelmap_setup',
## defined in conftest.py and used here via pytest magic
##

def test_fetch_supervoxels_for_body(labelmap_setup):
    dvid_server, dvid_repo, merge_table_path, mapping_path, _supervoxel_vol = labelmap_setup
    
    merge_graph = LabelmapMergeGraph(merge_table_path, mapping_path)
    _mut_id, supervoxels = merge_graph.fetch_supervoxels_for_body(dvid_server, dvid_repo, 'segmentation', 1)
    assert (sorted(supervoxels) == [1,2,3,4,5])


def test_fetch_and_apply_mapping(labelmap_setup):
    dvid_server, dvid_repo, merge_table_path, _mapping_path, _supervoxel_vol = labelmap_setup
    
    # Don't give mapping, ensure it's loaded from dvid.
    merge_graph = LabelmapMergeGraph(merge_table_path)
    merge_graph.fetch_and_apply_mapping(dvid_server, dvid_repo, 'segmentation')
    assert (merge_graph.merge_table_df['body'] == 1).all()


def test_extract_rows(labelmap_setup):
    dvid_server, dvid_repo, merge_table_path, mapping_path, _supervoxel_vol = labelmap_setup
    orig_merge_table = load_merge_table(merge_table_path, mapping_path, normalize=True)
    
    merge_graph = LabelmapMergeGraph(merge_table_path, mapping_path)

    r = requests.post(f'http://{dvid_server}/api/node/{dvid_repo}/branch', json={'branch': 'extract-rows-test'})
    r.raise_for_status()
    uuid = r.json()["child"]

    # First test: If nothing has changed in DVID, we get all rows.
    subset_df, dvid_supervoxels = merge_graph.extract_rows(dvid_server, dvid_repo, 'segmentation', 1)
    assert (dvid_supervoxels == [1,2,3,4,5]).all()
    assert (subset_df == orig_merge_table).all().all()

    # Now change the mapping in DVID and verify it is reflected in the extracted rows.
    # For this test, we'll cleave supervoxel 5 from the rest of the body.
    r = requests.post(f'http://{dvid_server}/api/node/{uuid}/segmentation/cleave/1', json=[5])
    r.raise_for_status()
    _cleaved_body = r.json()["CleavedLabel"]

    subset_df, dvid_supervoxels = merge_graph.extract_rows(dvid_server, uuid, 'segmentation', 1)
    assert (dvid_supervoxels == [1,2,3,4]).all()
    assert (subset_df == orig_merge_table.query('id_a != 5 and id_b != 5')).all().all()


def test_append_edges_for_split_supervoxels(labelmap_setup):
    dvid_server, dvid_repo, merge_table_path, _mapping_path, supervoxel_vol = labelmap_setup
    r = requests.post(f'http://{dvid_server}/api/node/{dvid_repo}/branch', json={'branch': 'split-test'})
    r.raise_for_status()
    uuid = r.json()["child"]
    
    # Split supervoxel 3 (see conftest.init_labelmap_nodes)
    # Remove the first column of pixels from it.
    
    # supervoxel 3 starts in column 6
    assert (supervoxel_vol == 3).nonzero()[2][0] == 6

    rle = [[6,0,0,1], # x,y,z,runlength
           [6,1,0,1],
           [6,2,0,1]]

    rle = np.array(rle, np.uint32)

    header = np.array([0,3,0,0], np.uint8)
    voxels = np.array([0], np.uint32)
    num_spans = np.array([len(rle)], np.uint32)
    payload = bytes(header) + bytes(voxels) + bytes(num_spans) + bytes(rle)

    r = requests.post(f'http://{dvid_server}/api/node/{uuid}/segmentation/split-supervoxel/3', data=payload)
    r.raise_for_status()
    split_response = r.json()
    split_sv = split_response["SplitSupervoxel"]
    remainder_sv = split_response["RemainSupervoxel"]
    split_mapping = np.array([[split_sv, 3],
                              [remainder_sv, 3]], np.uint64)

    merge_graph = LabelmapMergeGraph(merge_table_path)
    orig_table = merge_graph.merge_table_df.copy()
    
    merge_graph.append_edges_for_split_supervoxels(split_mapping, dvid_server, uuid, 'segmentation')
    #print(merge_graph.merge_table_df)
    assert merge_graph.merge_table_df.shape[0] == orig_table.shape[0] + 2
    
    # SV 3 was originally connected to SV 2 and 4.
    # We should have new rows for those connections, but with the new IDs
    assert len(merge_graph.merge_table_df.query('id_a == 2 and id_b == @split_sv')) == 1
    assert len(merge_graph.merge_table_df.query('id_a == 4 and id_b == @remainder_sv')) == 1
    
    #from libdvid import DVIDNodeService
    #ns = DVIDNodeService(dvid_server, uuid)
    #dvid_sv_vol = ns.get_labels3D('segmentation', (1,3,15), (0,0,0), supervoxels=True)
    #print(dvid_sv_vol)
    

if __name__ == "__main__":
    pytest.main(['--pyargs', 'neuclease.tests.test_merge_graph'])
