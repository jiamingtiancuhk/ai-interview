import History from './pages/History'
import Interview from './pages/Interview'
import Review from './pages/Review'
import Setup from './pages/Setup'
import { navigate, usePath } from './router'

function Nav() {
  return (
    <nav className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex max-w-3xl items-center gap-6 px-4 py-3 text-sm">
        <button onClick={() => navigate('/')} className="font-semibold">
          AI Interview
        </button>
        <button onClick={() => navigate('/')} className="text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
          新面试
        </button>
        <button onClick={() => navigate('/history')} className="text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
          记录
        </button>
      </div>
    </nav>
  )
}

export default function App() {
  const path = usePath()
  const [, page, id] = path.split('/')

  if (page === 'interview' && id) return <Interview id={id} />
  return (
    <>
      <Nav />
      {page === 'history' ? <History /> : page === 'review' && id ? <Review id={id} /> : <Setup />}
    </>
  )
}
