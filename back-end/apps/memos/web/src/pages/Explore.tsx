import MemoView from "@/components/MemoView";
import PagedMemoList from "@/components/PagedMemoList";
import { useMemoFilters, useMemoSorting } from "@/hooks";
import { State } from "@/types/proto/api/v1/common_pb";
import { Memo, Visibility } from "@/types/proto/api/v1/memo_service_pb";

const Explore = () => {
  // Explore only lists posts that other users have marked as PUBLIC.
  const visibilities = [Visibility.PUBLIC];

  // Build filter using unified hook (no creator scoping for Explore)
  const memoFilter = useMemoFilters({
    includeShortcuts: false,
    includePinned: false,
    visibilities,
  });

  // Get sorting logic using unified hook (no pinned sorting)
  const { listSort, orderBy } = useMemoSorting({
    pinnedFirst: false,
    state: State.NORMAL,
  });

  return (
    <PagedMemoList
      renderer={(memo: Memo) => <MemoView key={`${memo.name}-${memo.updateTime}`} memo={memo} showCreator showVisibility compact />}
      listSort={listSort}
      orderBy={orderBy}
      filter={memoFilter}
      showCreator
    />
  );
};

export default Explore;
