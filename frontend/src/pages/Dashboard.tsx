import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { ClaimRecord } from '../types'
import Spinner from '../components/Spinner'
import StatusBadge from '../components/StatusBadge'
import DemoBadge from '../components/DemoBadge'
import { PlusCircle, FileText, AlertCircle } from 'lucide-react'

export default function Dashboard() {
  const [claims, setClaims] = useState<ClaimRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.listClaims()
      .then((data) => { setClaims(data.claims); setTotal(data.total) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Overview of all demo claims <DemoBadge className="ml-1" /></p>
        </div>
        <Link
          to="/claims/new"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 transition-colors"
        >
          <PlusCircle className="w-4 h-4" /> New Claim
        </Link>
      </div>

      {/* Stats card */}
      <div className="grid sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-xl border p-5">
          <p className="text-sm text-gray-500">Total Demo Claims</p>
          <p className="text-3xl font-bold text-brand-700 mt-1">{loading ? '–' : total}</p>
        </div>
        <div className="bg-white rounded-xl border p-5">
          <p className="text-sm text-gray-500">Status</p>
          <p className="text-lg font-semibold text-green-700 mt-1">All Simulated</p>
        </div>
        <div className="bg-white rounded-xl border p-5">
          <p className="text-sm text-gray-500">Phase</p>
          <p className="text-lg font-semibold text-gray-700 mt-1">1 – MVP Demo</p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mb-6">
          <AlertCircle className="w-5 h-5 shrink-0" /> {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-20"><Spinner size="lg" /></div>
      )}

      {/* Empty state */}
      {!loading && !error && claims.length === 0 && (
        <div className="text-center py-20">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 mb-4">No demo claims yet.</p>
          <Link
            to="/claims/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700"
          >
            <PlusCircle className="w-4 h-4" /> Create your first claim
          </Link>
        </div>
      )}

      {/* Claims table */}
      {!loading && claims.length > 0 && (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3">Ticket ID</th>
                <th className="text-left px-4 py-3">Policy</th>
                <th className="text-left px-4 py-3">Vehicle</th>
                <th className="text-left px-4 py-3">Location</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {claims.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/claims/${c.id}`} className="text-brand-600 font-medium hover:underline">
                      {c.id}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{c.policy_reference}</td>
                  <td className="px-4 py-3 text-gray-700 capitalize">{c.vehicle_type}</td>
                  <td className="px-4 py-3 text-gray-700">{c.incident_location}</td>
                  <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                  <td className="px-4 py-3 text-gray-400">{new Date(c.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
