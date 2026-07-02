<script setup>
    import { faBan, faClockRotateLeft, faFileImport, faRotate, faTrash } from '@fortawesome/free-solid-svg-icons';
    import {
        fullReload,
        resetAllExerciseProgress,
        resetAll,
        resetLiveLogs,
        reloadFromDisk
    } from '@/socket'
    import { reduceMotionOn } from '@/settings.js'
</script>

<template>
    <div>
        <table class="">
            <tr class="">
                <td>
                    <label class="grid cursor-pointer place-items-center">
                        <input type="checkbox" v-model="reduceMotionOn" class="toggle toggle-info" />
                    </label>
                </td>
                <td class="text-lg">Reduce motion — calm animations for projection &amp; accessibility</td>
            </tr>
            <tr class="">
                <td>
                    <button @click="resetAllExerciseProgress()" class="h-10 min-h-10 font-semibold btn-danger btn gap-1">
                        <FontAwesomeIcon :icon="faClockRotateLeft" size="lg" fixed-width></FontAwesomeIcon>
                        Restart Exercises
                    </button>
                </td>
                <td class="text-lg">Restart exercises by marking all tasks incomplete</td>
            </tr>
            <tr class="">
                <td>
                    <button @click="resetAll()" class="h-10 min-h-10 font-semibold btn-danger btn gap-1">
                        <FontAwesomeIcon :icon="faTrash" size="lg" fixed-width></FontAwesomeIcon>
                        Reset All
                    </button>
                </td>
                <td class="text-lg">Reset the entire state. This will mark all task incomplete and clear all logs</td>
            </tr>
            <tr class="">
                <td>
                    <button @click="resetLiveLogs()" class="h-10 min-h-10 font-semibold btn-warning btn gap-1">
                        <FontAwesomeIcon :icon="faBan" size="lg" fixed-width></FontAwesomeIcon>
                        Clear Live Logs
                    </button>
                </td>
                <td class="text-lg">Clear logs from the Live Logs panel</td>
            </tr>
            <tr class="">
                <td>
                    <button @click="reloadFromDisk()" class="h-10 min-h-10 font-semibold btn-danger btn gap-1">
                        <FontAwesomeIcon :icon="faFileImport" size="lg" fixed-width></FontAwesomeIcon>
                        Reload Scenarios From Disk
                    </button>
                </td>
                <td class="text-lg">Reload all scenarios from the disk and reset the entire state</td>
            </tr>
        </table>
    </div>
</template>

<style scoped>
table td {
    @apply px-2 py-1
}
</style>