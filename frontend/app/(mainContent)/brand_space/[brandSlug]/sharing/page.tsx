import ShareReviewScreen from "@/components/sharing/ShareReviewScreen";

export default function SharingPage({
  params,
  searchParams,
}: {
  params: { brandSlug: string };
  searchParams: { token?: string };
}) {
  return <ShareReviewScreen brandKey={params.brandSlug} reviewToken={searchParams.token} />;
}
