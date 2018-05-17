import os
import csv
import logging

import h5py
import numpy as np
import pandas as pd

from dvidutils import LabelMapper

from .util import Timer

logger = logging.getLogger(__name__)


MERGE_TABLE_DTYPE = [('id_a', '<u8'),
                     ('id_b', '<u8'),
                     ('xa', '<u4'),
                     ('ya', '<u4'),
                     ('za', '<u4'),
                     ('xb', '<u4'),
                     ('yb', '<u4'),
                     ('zb', '<u4'),
                     ('score', '<f4')]

MAPPED_MERGE_TABLE_DTYPE = MERGE_TABLE_DTYPE + [('body', '<u8')]

def load_merge_table(path, mapping=None, normalize=True, set_multiindex=False, scores_only=False):
    """
    Load the merge table from the given path (preferably '.npy' in FFN format),
    and return it as a DataFrame, with an appended a 'body' column according to the given mapping.
    Args:
        path:
            Either .npy (with FFN-style columns) or .csv (with CELIS-style columns)
        
        mapping:
            Either None, a pd.Series (index is SV, value is body), or a path from which one can be loaded.
            Assign 'body' column according to the given mapping of SV->body.
            Only id_a is considered when applying the mapping to each edge.
            If None, the returned 'body' column will be zero for all rows.
    
        normalize:
            If True, ensure that id_a < id_b for all edges (and ensure no self-edges)
        
        set_multiindex:
            If True, copy (id_a,id_b) to the index, and sort by the index.
            Allows pandas MultiIndex-based selection.
        
        scores_only:
            If True, discard coordinate columns
        
    Returns:
        DataFrame.
        If scores_only=True: columns=['id_a', 'id_b', 'score', 'body']
        If scores_only=False, columns=['id_a', 'id_b', 'xa', 'ya', 'za', 'xb', 'yb', 'zb', 'score', 'body']
    """
    ext = os.path.splitext(path)[1]
    assert ext in ('.npy', '.csv'), f"Invalid file extension: {ext}"
    
    sort_by = None
    if set_multiindex:
        # MultiIndex selection requires a sorted index
        # It's faster to sort the array in-place now, before converting to DataFrame
        sort_by = ['id_a', 'id_b']
    
    if ext == '.npy':
        merge_table_df = load_ffn_merge_table(path, normalize, sort_by)
    elif ext == '.csv':
        merge_table_df = load_celis_csv(path, normalize, sort_by)

    if scores_only:
        merge_table_df = merge_table_df[['id_a', 'id_b', 'score']].copy()

    if set_multiindex:
        # (Note that the table is already sorted by now)
        idx_columns = (merge_table_df['id_a'], merge_table_df['id_b'])
        merge_table_df.index = pd.MultiIndex.from_arrays(idx_columns, names=['idx_a', 'idx_b'])
    
    if mapping is None:
        merge_table_df['body'] = np.zeros((len(merge_table_df),), dtype=np.uint64)
    else:
        apply_mapping_to_mergetable(merge_table_df, mapping)
    return merge_table_df


def apply_mapping_to_mergetable(merge_table_df, mapping):
    """
    Set the 'body' column of the given merge table (append one if it didn't exist)
    by applying the given SV->body mapping to the merge table's id_a column.
    """
    if isinstance(mapping, str):
        with Timer("Loading mapping", logger):
            mapping = load_mapping(mapping)

    assert isinstance(mapping, pd.Series), "Mapping must be a pd.Series"        
    with Timer("Applying mapping to merge table", logger):
        mapper = LabelMapper(mapping.index.values, mapping.values)
        body_a = mapper.apply(merge_table_df['id_a'].values, allow_unmapped=True)
        body_b = mapper.apply(merge_table_df['id_b'].values, allow_unmapped=True)

        # Cut edges that span across bodies
        body_a[body_a != body_b] = 0
        merge_table_df['body'] = body_a

def load_celis_csv(csv_path, normalize=True, sort_by=None):
    """
    Jeremy's CELIS exports are given in CSV format, with the following columns:
    segment_a,segment_b,score,x,y,z
    
    This isn't sufficient for every use-case because we
    would prefer to have TWO representative coordinates for the merge,
    on both sides of the merge boundary.
    
    But for testing purposes, we'll just duplicate the coordinate
    columns to provide the same columns that an FFN merge table provides.
    
    Returns a DataFrame with columns:
        ['id_a', 'id_b', 'xa', 'ya', 'za', 'xb', 'yb', 'zb', 'score']
    """
    assert os.path.splitext(csv_path)[1] == '.csv'
    with open(csv_path, 'r') as csv_file:
        # Is there a header?
        has_header = csv.Sniffer().has_header(csv_file.read(1024))
        if not has_header:
            raise RuntimeError(f"{csv_path} has no header row")

    df = pd.read_csv(csv_path, header=0, usecols=['segment_a,segment_b,score,x,y,z'], engine='c')
    df = df[['segment_a', 'segment_b', 'x', 'y', 'z', 'x', 'y', 'z', 'score']]
    df.columns = ['id_a', 'id_b', 'xa', 'ya', 'za', 'xb', 'yb', 'zb', 'score']

    if normalize:
        mt = df.to_records(index=False)
        mt = normalize_merge_table(mt)
        df = pd.DataFrame(mt)

    if sort_by:
        mt.sort_values(sort_by, inplace=True)
    
    return df


def load_ffn_merge_table(npy_path, normalize=True, sort_by=None):
    """
    Load the FFN merge table from the given .npy file,
    and return it as a DataFrame.
    
    If normalize=True, ensure the following:
    - no 'loops', i.e. id_a != id_b for all edges
    - no duplicate edges
    - id_a < id_b for all edges
    
    Returns a DataFrame with columns:
        ['id_a', 'id_b', 'xa', 'ya', 'za', 'xb', 'yb', 'zb', 'score']
    """
    assert os.path.splitext(npy_path)[1] == '.npy'
    merge_table = np.load(npy_path)
    assert merge_table.dtype == MERGE_TABLE_DTYPE
    
    if normalize:
        merge_table = normalize_merge_table(merge_table)

    if sort_by:
        merge_table.sort(0, order=sort_by)
    
    return pd.DataFrame(merge_table)


def load_mapping(path):
    ext = os.path.splitext(path)[1]
    assert ext in ('.csv', '.npy')
    if ext == '.csv':
        mapping = load_edge_csv(path)
    elif ext == '.npy':
        mapping = np.load(path)
    
    mapping_series = pd.Series(index=mapping[:,0], data=mapping[:,1])
    mapping_series.index.name = 'sv'
    mapping_series.name = 'body'
    return mapping_series


def load_edge_csv(csv_path):
    """
    Load and return the given edge list CSV file as a numpy array.
    
    Each row represents an edge. For example:
    
        123,456
        123,789
        789,234
    
    The CSV file may optionally contain a header row.
    Also, it may contain more than two columns, but only the first two columns are used.
    
    Returns:
        ndarray with shape (N,2)
    """
    with open(csv_path, 'r') as csv_file:
        # Is there a header?
        has_header = csv.Sniffer().has_header(csv_file.read(1024))
        csv_file.seek(0)
        rows = iter(csv.reader(csv_file))
        if has_header:
            # Skip header
            _header = next(rows)
        
        # We only care about the first two columns
        df = pd.read_csv(csv_file, usecols=[0,1], header=None, names=['u', 'v'], dtype=np.uint64, engine='c')
        edges = df.values
        assert edges.dtype == np.uint64
        assert edges.shape[1] == 2

    return edges


def swap_cols(table, rows, name_a, name_b):
    """
    Swap two columns of a structured array, in-place.
    """
    col_a = table[name_a][rows]
    col_b = table[name_b][rows]
    
    # Swap dtypes to avoid assignment error
    col_a, col_b = col_a.view(col_b.dtype), col_b.view(col_a.dtype)

    table[name_a][rows] = col_b
    table[name_b][rows] = col_a


def normalize_merge_table(merge_table, drop_duplicate_edges=True, sort=None):
    """
    'Normalize' the given merge table by ensuring that id_a <= id_b for all rows,
    swapping fields as needed.
    
    If drop_duplicate_edges=True, duplicate edges will be dropped,
    without regard to any of the other columns (e.g. two rows with
    identical edges but different scores are still considered duplicates).
    """
    assert merge_table.dtype == MERGE_TABLE_DTYPE, f"Table has wrong dtype: {merge_table.dtype}"

    # Group the A coords and the B coords so they can be swapped together
    grouped_dtype = [('id_a', '<u8'),
                     ('id_b', '<u8'),
                     ('loc_a', [('xa', '<u4'), ('ya', '<u4'), ('za', '<u4')]),
                     ('loc_b', [('xb', '<u4'), ('yb', '<u4'), ('zb', '<u4')]),
                     ('score', '<f4')]

    swap_rows = merge_table['id_a'] > merge_table['id_b']
    merge_table_grouped = merge_table.view(grouped_dtype)
    
    swap_cols(merge_table_grouped, swap_rows, 'id_a', 'id_b')
    swap_cols(merge_table_grouped, swap_rows, 'loc_a', 'loc_b')

    assert (merge_table['id_a'] <= merge_table['id_b']).all()

    if drop_duplicate_edges:
        edge_df = pd.DataFrame( {'id_a': merge_table['id_a'], 'id_b': merge_table['id_b']} )
        dupe_rows = edge_df.duplicated(keep='last')
        if dupe_rows.sum() > 0:
            merge_table = merge_table[~dupe_rows]
    
    if sort is not None:
        merge_table.sort(order=sort)
    
    return merge_table

def apply_mappings(supervoxels, mappings):
    assert isinstance(mappings, dict)
    df = pd.DataFrame(index=supervoxels.astype(np.uint64, copy=False))
    df.index.name = 'sv'

    for name, mapping in mappings.items():
        assert isinstance(mapping, pd.Series)
        index_values = mapping.index.values.astype(np.uint64, copy=False)
        mapping_values = mapping.values.astype(np.uint64, copy=False)
        mapper = LabelMapper(index_values, mapping_values)
        df[name] = mapper.apply(df.index.values, allow_unmapped=True)

    return df

def load_supervoxel_sizes(h5_path):
    """
    Load the stored supervoxel size table from hdf5 and return the result as a pd.Series, with sv as the index.
    
    h5_path: A file with two datasets: sv_ids and sv_sizes
    """
    with h5py.File(h5_path, 'r') as f:
        sv_sizes = pd.Series(index=f['sv_ids'][:], data=f['sv_sizes'][:])
    sv_sizes.name = 'voxel_count'
    sv_sizes.index.name = 'sv'

    logger.info(f"Volume contains {len(sv_sizes)} supervoxels and {sv_sizes.values.sum()/1e12:.1f} Teravoxels in total")    

    # Sorting by supervoxel ID may give better performance during merges later
    sv_sizes.sort_index(inplace=True)
    return sv_sizes

def compute_body_sizes(sv_sizes, mapping):
    """
    Given a Series of supervoxel sizes and an sv-to-body mapping,
    compute the size of each body in the mapping.
    
    Any supervoxels in the mapping that are missing from sv_sizes will be ignored.
    
    Returns: Series, indexed by body.
    """
    if isinstance(sv_sizes, str):
        logger.info("Loading supervoxel sizes")
        assert os.path.splitext(sv_sizes)[1] == '.h5'
        sv_sizes = load_supervoxel_sizes(sv_sizes)
    
    if isinstance(mapping, str):
        logger.info("Loading mapping")
        mapping = load_mapping(mapping)
    
    assert isinstance(sv_sizes, pd.Series)
    assert isinstance(mapping, pd.Series)
    
    assert sv_sizes.index.dtype == np.uint64
    
    sv_sizes = sv_sizes.astype(np.uint64)
    mapper = LabelMapper(sv_sizes.index.values, sv_sizes.values)

    # Just drop SVs that we don't have sizes for.
    logger.info("Dropping unknown supervoxels")
    mapping = mapping.loc[mapping.index.isin(sv_sizes.index)]

    logger.info("Applying sizes to mapping")
    df = pd.DataFrame({'body': mapping})
    df['voxel_count'] = mapper.apply(mapping.index.values)

    logger.info("Aggregating sizes by body")
    body_sizes = df.groupby('body').sum()['voxel_count']
    body_sizes.sort_values(inplace=True, ascending=False)
    return body_sizes




