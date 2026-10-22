import { useRef, type ReactNode } from 'react';

export type ReadingTab = 'transcript' | 'favorites' | 'questions';
const tabs: Array<{ id: ReadingTab; label: string }> = [
  { id: 'transcript', label: '字幕' },
  { id: 'favorites', label: '我的收藏' },
  { id: 'questions', label: '我的提问' },
];

interface Props {
  activeTab: ReadingTab;
  onTabChange: (tab: ReadingTab) => boolean | void;
  transcript: ReactNode;
  favorites: ReactNode;
  questions: ReactNode;
}

export default function ReadingNotesWorkspace({ activeTab, onTabChange,
  transcript, favorites, questions }: Props) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  const content = { transcript, favorites, questions };
  return <>
    <div className="reading-tabs" role="tablist" aria-label="视频学习内容">
      {tabs.map((tab, index) => <button key={tab.id} type="button" role="tab"
        id={`reading-tab-${tab.id}`} aria-controls={`reading-panel-${tab.id}`}
        aria-selected={activeTab === tab.id} tabIndex={activeTab === tab.id ? 0 : -1}
        ref={button => { buttons.current[index] = button; }}
        onClick={() => onTabChange(tab.id)}
        onKeyDown={event => {
          let next: number;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = tabs.length - 1;
          else return;
          event.preventDefault();
          if (onTabChange(tabs[next].id) !== false) buttons.current[next]?.focus();
        }}>{tab.label}</button>)}
    </div>
    <div className="reading-tab-content">
      {tabs.map(tab => <section key={tab.id} className="reading-tab-panel"
        id={`reading-panel-${tab.id}`} role="tabpanel" aria-labelledby={`reading-tab-${tab.id}`}
        data-active={activeTab === tab.id} aria-hidden={activeTab !== tab.id}
        inert={activeTab !== tab.id} tabIndex={0}>
        {content[tab.id]}
      </section>)}
    </div>
  </>;
}
