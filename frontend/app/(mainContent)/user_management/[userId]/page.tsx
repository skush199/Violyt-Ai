import UserEditorForm from "@/components/userManagement/UserEditorForm";
import UserOverview from "@/components/userManagement/UserOverview";

export default function UserDetailPage({
  params,
  searchParams,
}: {
  params: { userId: string };
  searchParams: { edit?: string };
}) {
  return searchParams.edit === "true" ? (
    <UserEditorForm mode="edit" userId={params.userId} />
  ) : (
    <UserOverview userId={params.userId} />
  );
}
