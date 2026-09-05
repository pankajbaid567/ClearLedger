"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_PAGE_SIZES = [5, 10, 15, 25, 50];

export type DataTableColumn<T> = {
  key: string;
  label: string;
  render: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number;
  className?: string;
  compact?: boolean;
};

export function DataTable<T>({
  rows,
  columns,
  getRowKey,
  onRowClick,
  pageSize = 15,
  pageSizeOptions = DEFAULT_PAGE_SIZES,
  filterText,
  filterPlaceholder = "Filter table",
  emptyMessage = "No records match the current filters.",
  testId,
  query: controlledQuery,
  onQueryChange,
}: {
  rows: T[];
  columns: DataTableColumn<T>[];
  getRowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  pageSize?: number;
  pageSizeOptions?: number[];
  filterText?: (row: T) => string;
  filterPlaceholder?: string;
  emptyMessage?: string;
  testId?: string;
  query?: string;
  onQueryChange?: (query: string) => void;
}) {
  const [localQuery, setLocalQuery] = useState("");
  const query = controlledQuery ?? localQuery;
  const setQuery = onQueryChange ?? setLocalQuery;
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize);
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);
  const tableStartRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const subset =
      normalized && filterText
        ? rows.filter((row) => filterText(row).toLowerCase().includes(normalized))
        : rows;
    if (!sort) return subset;
    const column = columns.find((item) => item.key === sort.key);
    if (!column?.sortValue) return subset;
    return [...subset].sort((left, right) => {
      const leftValue = column.sortValue?.(left) ?? "";
      const rightValue = column.sortValue?.(right) ?? "";
      const comparison =
        typeof leftValue === "number" && typeof rightValue === "number"
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue));
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [columns, filterText, query, rows, sort]);

  const availablePageSizes = useMemo(
    () => [...new Set([...pageSizeOptions, pageSize])].sort((left, right) => left - right),
    [pageSize, pageSizeOptions],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / rowsPerPage));
  const currentPage = Math.min(page, pages);
  const visibleRows = filtered.slice(
    (currentPage - 1) * rowsPerPage,
    currentPage * rowsPerPage,
  );

  useEffect(() => setRowsPerPage(pageSize), [pageSize]);
  useEffect(() => setPage(1), [query, rows, rowsPerPage]);
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  function goToPage(nextPage: number) {
    const boundedPage = Math.min(pages, Math.max(1, nextPage));
    if (boundedPage === currentPage) return;
    setPage(boundedPage);
    window.requestAnimationFrame(() => {
      const tableTop = tableStartRef.current?.getBoundingClientRect().top;
      if (tableTop === undefined) return;
      window.scrollTo({ top: window.scrollY + tableTop - 88, behavior: "smooth" });
    });
  }

  function toggleSort(column: DataTableColumn<T>) {
    if (!column.sortValue) return;
    setSort((current) =>
      current?.key === column.key
        ? { key: column.key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key: column.key, direction: "asc" },
    );
  }

  return (
    <div className="min-w-0" data-testid={testId} ref={tableStartRef}>
      {filterText ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e2e8f0] bg-[#f8fafc] px-4 py-3">
          <label className="relative block min-w-[220px] max-w-md flex-1">
            <span className="sr-only">{filterPlaceholder}</span>
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#94a3b8]"
              size={15}
            />
            <input
              className="input pl-9 text-[0.76rem] border-[#cbd5e1] focus:border-[#0c44ac] focus:ring-2 focus:ring-[#0c44ac]/10"
              onChange={(event) => setQuery(event.target.value)}
              placeholder={filterPlaceholder}
              value={query}
            />
          </label>
          <span className="text-[0.67rem] font-bold text-[#64748b] tabular-nums uppercase tracking-wider">
            {filtered.length} {filtered.length === 1 ? "record" : "records"}
          </span>
        </div>
      ) : null}
      <div className="space-y-3 p-3 md:hidden" aria-label="Compact records">
        {visibleRows.map((row) => <article className="rounded-lg border border-slate-200 bg-white p-3" key={getRowKey(row)}>
          <dl className="space-y-2">{columns.filter((c) => c.compact || columns.filter((x) => x.compact).length === 0).slice(0, 5).map((column) => <div className="flex items-start justify-between gap-3 text-xs" key={column.key}><dt className="text-slate-500">{column.label}</dt><dd className="m-0 text-right">{column.render(row)}</dd></div>)}</dl>
          {onRowClick ? <button type="button" className="btn btn-secondary mt-3 w-full" onClick={() => onRowClick(row)}>Inspect {getRowKey(row)}</button> : null}
        </article>)}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[680px] border-collapse text-left text-[0.73rem]">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-[#e2e8f0] bg-[#f8fafc] text-[#475569] text-[0.68rem] font-bold uppercase tracking-wider">
              {columns.map((column) => {
                const activeSort = sort?.key === column.key ? sort.direction : null;
                return (
                  <th
                    aria-sort={activeSort ? (activeSort === "asc" ? "ascending" : "descending") : undefined}
                    className={`h-11 px-4 py-2.5 font-bold ${column.className ?? ""}`}
                    key={column.key}
                  >
                    {column.sortValue ? (
                      <button
                        className={`inline-flex items-center gap-1.5 whitespace-nowrap ${
                          activeSort ? "text-[#0c44ac]" : "hover:text-[#0f172a]"
                        }`}
                        onClick={() => toggleSort(column)}
                        type="button"
                      >
                        {column.label}
                        {activeSort === "asc" ? (
                          <ArrowUp aria-hidden="true" size={12} className="text-[#0c44ac]" />
                        ) : activeSort === "desc" ? (
                          <ArrowDown aria-hidden="true" size={12} className="text-[#0c44ac]" />
                        ) : (
                          <ChevronsUpDown aria-hidden="true" className="text-[#94a3b8]" size={12} />
                        )}
                      </button>
                    ) : (
                      <span className="whitespace-nowrap">{column.label}</span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr
                className={`border-b border-[#f1f5f9] bg-white last:border-0 ${
                  onRowClick
                    ? "cursor-pointer transition-colors duration-150 hover:bg-[#f0f7ff] focus:bg-[#f0f7ff] focus:outline-none focus-visible:shadow-[inset_3px_0_0_#0c44ac]"
                    : ""
                }`}
                data-row-key={getRowKey(row)}
                key={getRowKey(row)}
                onClick={() => onRowClick?.(row)}

              >
                {columns.map((column, columnIndex) => (
                  <td className={`px-4 py-3.5 align-middle text-[#334155] ${column.className ?? ""}`} key={column.key}>
                    {onRowClick && columnIndex === 0 ? <button className="text-left underline decoration-slate-300 underline-offset-4 focus-visible:outline-2 focus-visible:outline-blue-600" type="button" aria-label={`Inspect ${getRowKey(row)}`} onClick={(event) => { event.stopPropagation(); onRowClick(row); }}>{column.render(row)}</button> : column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!visibleRows.length ? (
          <div className="flex min-h-48 flex-col items-center justify-center gap-3 px-6 text-center text-[0.78rem] text-[#64748b]">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f1f5f9] text-[#64748b]">
              <Search aria-hidden="true" size={17} />
            </span>
            <span>{emptyMessage}</span>
          </div>
        ) : null}
      </div>
      <div className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-t border-[#e2e8f0] bg-[#f8fafc] px-4 py-2 text-[0.69rem] text-[#64748b]">
        <span className="tabular-nums font-medium" data-testid="pagination-range">
          {filtered.length ? (currentPage - 1) * rowsPerPage + 1 : 0}–
          {Math.min(currentPage * rowsPerPage, filtered.length)} of{" "}
          {filtered.length}
        </span>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <label className="flex items-center gap-2 whitespace-nowrap font-semibold text-[#475569]">
            Rows per page
            <select
              aria-label="Rows per page"
              className="h-8 rounded-[6px] border border-[#cbd5e1] bg-white px-2 text-[0.69rem] font-semibold text-[#0f172a] shadow-xs"
              onChange={(event) => setRowsPerPage(Number(event.target.value))}
              value={rowsPerPage}
            >
              {availablePageSizes.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center gap-1">
            <button
              aria-label="Previous page"
              className="btn btn-secondary btn-icon h-8 w-8 min-h-0 rounded-[6px]"
              disabled={currentPage <= 1}
              onClick={() => goToPage(currentPage - 1)}
              type="button"
            >
              <ChevronLeft aria-hidden="true" size={14} />
            </button>
            <span className="px-2 text-[0.69rem] font-bold text-[#0f172a]" data-testid="pagination-status" role="status" aria-live="polite">
              {pages === 1 ? `All ${filtered.length} matching records` : `Page ${currentPage} of ${pages}`}
            </span>
            <button
              aria-label="Next page"
              className="btn btn-secondary btn-icon h-8 w-8 min-h-0 rounded-[6px]"
              disabled={currentPage >= pages}
              onClick={() => goToPage(currentPage + 1)}
              type="button"
            >
              <ChevronRight aria-hidden="true" size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
