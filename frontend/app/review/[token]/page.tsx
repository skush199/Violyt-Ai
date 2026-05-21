import ShareReviewScreen from "@/components/sharing/ShareReviewScreen";

export default function PublicReviewPage({
  params,
}: {
  params: { token: string };
}) {
  return <ShareReviewScreen reviewToken={params.token} externalMode />;
}
