import { useState, useCallback } from 'react';

export interface UseExpandableTableReturn {
  expandedRowKeys: string[];
  toggleRow: (key: string) => void;
  expandAll: (keys: string[]) => void;
  collapseAll: () => void;
  isExpanded: (key: string) => boolean;
  setExpandedRowKeys: React.Dispatch<React.SetStateAction<string[]>>;
}

/**
 * Hook for managing expandable table rows
 *
 * @example
 * const { expandedRowKeys, toggleRow, isExpanded } = useExpandableTable()
 *
 * // In table config
 * expandable={{
 *   expandedRowKeys,
 *   onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[])
 * }}
 *
 * // Toggle on row click
 * onRow={(record) => ({
 *   onClick: () => toggleRow(record.id)
 * })}
 */
export function useExpandableTable(initialKeys: string[] = []): UseExpandableTableReturn {
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>(initialKeys);

  const toggleRow = useCallback((key: string) => {
    setExpandedRowKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }, []);

  const expandAll = useCallback((keys: string[]) => {
    setExpandedRowKeys(keys);
  }, []);

  const collapseAll = useCallback(() => {
    setExpandedRowKeys([]);
  }, []);

  const isExpanded = useCallback(
    (key: string) => {
      return expandedRowKeys.includes(key);
    },
    [expandedRowKeys]
  );

  return {
    expandedRowKeys,
    toggleRow,
    expandAll,
    collapseAll,
    isExpanded,
    setExpandedRowKeys,
  };
}
