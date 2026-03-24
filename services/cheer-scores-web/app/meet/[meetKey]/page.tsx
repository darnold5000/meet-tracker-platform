import { MvpMeetPage } from "@/components/MvpMeetPage";

type Props = { params: Promise<{ meetKey: string }> };

export default async function MeetRoute({ params }: Props) {
  const { meetKey } = await params;
  return (
    <main>
      <MvpMeetPage meetKey={decodeURIComponent(meetKey)} />
    </main>
  );
}
